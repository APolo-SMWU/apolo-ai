"""GitHub 공개 Profile·Repository 수집"""

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote, unquote, urlparse

import httpx    # GitHub API 요청

from apolo.contracts.source import CollectedSource, EvidenceCandidate

# 프로필당 Repository는 최대 20개, README는 표시된 크기 기준 200,000바이트로 제한
GITHUB_API_URL = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"
MAX_PROFILE_REPOSITORIES = 20
MAX_README_BYTES = 200_000


class GitHubCollectionError(RuntimeError):
    """GitHub Collector 오류 처리"""

    def __init__(
        self,
        code: Literal[
            "unsupported_url", "not_found", "rate_limited", "unavailable", "invalid_response"
        ],
        message: str,
    ) -> None:
        """오류 코드·메시지 보관"""
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class GitHubCollectionWarning:
    """부분 수집 실패 경고 정보"""

    source_url: str
    code: str
    message: str


@dataclass(frozen=True)
class GitHubCollectionResult:
    """GitHub URL 수집 결과"""

    sources: list[CollectedSource]
    warnings: list[GitHubCollectionWarning]


@dataclass(frozen=True)
class _GitHubTarget:
    """GitHub URL 파싱 대상"""

    kind: Literal["profile", "repository"]
    owner: str
    repository: str | None = None


async def collect_github_source(
    source_url: str, *, client: httpx.AsyncClient
) -> CollectedSource:
    """Profile·Repository 단일 Source 수집"""
    target, payload = await _fetch_target_payload(source_url, client=client)
    return _normalize_target(target, payload)


async def collect_github_sources(
    source_url: str, *, client: httpx.AsyncClient
) -> GitHubCollectionResult:
    """Profile·Repository·README 묶음 수집"""
    target, payload = await _fetch_target_payload(source_url, client=client)
    if target.kind == "repository":
        source, warning = await _repository_source_with_readme(payload, client=client)
        return GitHubCollectionResult(
            sources=[source], warnings=[warning] if warning is not None else []
        )

    profile = _normalize_target(target, payload)
    warnings: list[GitHubCollectionWarning] = []
    try:
        repositories = await _list_profile_repositories(target.owner, client=client)
    except GitHubCollectionError as error:
        warnings.append(_warning_from_error(profile.source_url, error))
        return GitHubCollectionResult(sources=[profile], warnings=warnings)

    if len(repositories) > MAX_PROFILE_REPOSITORIES:
        warnings.append(
            GitHubCollectionWarning(
                source_url=profile.source_url,
                code="repository_limit",
                message=f"최근 Repository {MAX_PROFILE_REPOSITORIES}개만 수집했습니다.",
            )
        )

    sources = [profile]
    selected_repositories = repositories[:MAX_PROFILE_REPOSITORIES]
    readme_rate_limited = False
    for index, repository in enumerate(selected_repositories):
        if readme_rate_limited:
            try:
                sources.append(_repository_source_without_readme(repository))
            except GitHubCollectionError as error:
                warnings.append(_warning_from_error(profile.source_url, error))
            continue
        try:
            source, warning = await _repository_source_with_readme(repository, client=client)
            sources.append(source)
            if warning is not None:
                warnings.append(warning)
                if warning.code == "rate_limited":
                    readme_rate_limited = True
                    remaining = len(selected_repositories) - index - 1
                    if remaining:
                        warnings.append(
                            GitHubCollectionWarning(
                                source_url=profile.source_url,
                                code="readme_skipped_after_rate_limit",
                                message=(
                                    f"남은 Repository {remaining}개의 README 수집을 건너뛰었습니다."
                                ),
                            )
                        )
        except GitHubCollectionError as error:
            warnings.append(_warning_from_error(profile.source_url, error))
    return GitHubCollectionResult(sources=sources, warnings=warnings)


def normalize_profile(payload: Mapping[str, Any]) -> CollectedSource:
    """GitHub `GET /users/{username}` 응답의 Profile Source 변환"""
    github_id = _required_int(payload, "id")
    login = _required_text(payload, "login")
    source_url = _required_text(payload, "html_url")

    fields = [("login", login)]
    for field in ("name", "bio", "company", "location", "blog"):
        value = _optional_text(payload, field)
        if value is not None:
            fields.append((field, value))

    return _collected_source(
        source_key=f"github:profile:{github_id}",
        source_url=source_url,
        source_version=_optional_text(payload, "updated_at"),
        title=f"GitHub Profile: {login}",
        fields=fields,
    )


def normalize_repository(
    payload: Mapping[str, Any], *, readme_content: str | None = None
) -> CollectedSource:
    """GitHub `GET /repos/{owner}/{repo}` 응답의 Repository Source 변환"""
    github_id = _required_int(payload, "id")
    full_name = _required_text(payload, "full_name")
    source_url = _required_text(payload, "html_url")

    fields = [("full_name", full_name)]
    for field in ("description", "homepage", "language"):
        value = _optional_text(payload, field)
        if value is not None:
            fields.append((field, value))

    topics = _optional_topics(payload)
    evidence_fields = list(fields)
    if topics:
        fields.append(("topics", ", ".join(topics)))
        evidence_fields.extend((f"topics[{index}]", topic) for index, topic in enumerate(topics))

    source = _collected_source(
        source_key=f"github:repository:{github_id}",
        source_url=source_url,
        source_version=_optional_text(payload, "updated_at")
        or _optional_text(payload, "pushed_at"),
        title=f"GitHub Repository: {full_name}",
        fields=fields,
        evidence_fields=evidence_fields,
    )
    if readme_content is None:
        return source
    return source.model_copy(
        update={
            "content": f"{source.content}\n\n## README\n\n{readme_content}",
            "evidence_candidates": [
                *source.evidence_candidates,
                EvidenceCandidate(snippet=readme_content, locator="github.readme"),
            ],
        }
    )


async def _fetch_target_payload(
    source_url: str, *, client: httpx.AsyncClient
) -> tuple[_GitHubTarget, Mapping[str, Any]]:
    """URL 대상과 GitHub API 응답 조회"""
    target = _parse_target(source_url)
    path = _target_path(target)
    payload = await _get_json(client, path)
    if not isinstance(payload, Mapping):
        raise GitHubCollectionError("invalid_response", "GitHub API 응답 형식이 올바르지 않습니다.")
    return target, payload


def _normalize_target(target: _GitHubTarget, payload: Mapping[str, Any]) -> CollectedSource:
    """대상 종류별 Source 정규화"""
    try:
        if target.kind == "profile":
            return normalize_profile(payload)
        return normalize_repository(payload)
    except ValueError as error:
        raise GitHubCollectionError("invalid_response", str(error)) from error


async def _list_profile_repositories(
    owner: str, *, client: httpx.AsyncClient
) -> list[Mapping[str, Any]]:
    """소유자 Repository 최신 목록 조회"""
    payload = await _get_json(
        client,
        f"/users/{_path_segment(owner)}/repos",
        params={
            "type": "owner",
            "sort": "updated",
            "per_page": MAX_PROFILE_REPOSITORIES + 1,
        },
    )
    valid_repositories = isinstance(payload, list) and all(
        isinstance(repository, Mapping) for repository in payload
    )
    if not valid_repositories:
        raise GitHubCollectionError(
            "invalid_response", "GitHub Repository 목록 형식이 올바르지 않습니다."
        )
    return payload


async def _repository_source_with_readme(
    payload: Mapping[str, Any], *, client: httpx.AsyncClient
) -> tuple[CollectedSource, GitHubCollectionWarning | None]:
    """Repository·README Source 결합"""
    source = _repository_source_without_readme(payload)
    try:
        owner, repository = _repository_parts(_required_text(payload, "full_name"))
    except ValueError as error:
        raise GitHubCollectionError("invalid_response", str(error)) from error

    readme_content, warning = await _fetch_readme(
        owner, repository, source_url=source.source_url, client=client
    )
    if readme_content is None:
        return source, warning
    try:
        return normalize_repository(payload, readme_content=readme_content), warning
    except ValueError as error:
        raise GitHubCollectionError("invalid_response", str(error)) from error


def _repository_source_without_readme(payload: Mapping[str, Any]) -> CollectedSource:
    """README 제외 Repository Source 정규화"""
    try:
        return normalize_repository(payload)
    except ValueError as error:
        raise GitHubCollectionError("invalid_response", str(error)) from error


async def _fetch_readme(
    owner: str,
    repository: str,
    *,
    source_url: str,
    client: httpx.AsyncClient,
) -> tuple[str | None, GitHubCollectionWarning | None]:
    """Repository README 수집·경고 변환"""
    try:
        payload = await _get_json(
            client,
            f"/repos/{_path_segment(owner)}/{_path_segment(repository)}/readme",
        )
    except GitHubCollectionError as error:
        if error.code == "not_found":
            return None, None
        return None, _warning_from_error(source_url, error)

    try:
        return _decode_readme(payload), None
    except ValueError as error:
        return None, GitHubCollectionWarning(
            source_url=source_url,
            code="invalid_readme",
            message=str(error),
        )


def _decode_readme(payload: object) -> str | None:
    """Base64 README 텍스트 변환"""
    if not isinstance(payload, Mapping):
        raise ValueError("GitHub README 응답 형식이 올바르지 않습니다.")
    if payload.get("encoding") != "base64":
        raise ValueError("GitHub README 인코딩을 지원하지 않습니다.")
    size = payload.get("size")
    content = payload.get("content")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError("GitHub README 크기 정보가 올바르지 않습니다.")
    if size > MAX_README_BYTES:
        raise ValueError(f"GitHub README는 {MAX_README_BYTES} bytes 이하만 수집합니다.")
    if not isinstance(content, str):
        raise ValueError("GitHub README 본문이 없습니다.")
    try:
        decoded = base64.b64decode("".join(content.split()), validate=True)
        readme = decoded.decode("utf-8")
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("GitHub README를 UTF-8 텍스트로 읽을 수 없습니다.") from error
    return readme if readme.strip() else None


async def _get_json(
    client: httpx.AsyncClient, path: str, *, params: Mapping[str, str | int] | None = None
) -> object:
    """GitHub API JSON 요청"""
    try:
        response = await client.get(
            f"{GITHUB_API_URL}{path}",
            params=params,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
            },
        )
    except httpx.RequestError as error:
        raise GitHubCollectionError("unavailable", "GitHub API에 연결하지 못했습니다.") from error

    _raise_for_status(response)
    try:
        return response.json()
    except ValueError as error:
        raise GitHubCollectionError(
            "invalid_response", "GitHub API 응답이 JSON이 아닙니다."
        ) from error


def _target_path(target: _GitHubTarget) -> str:
    """대상별 GitHub API 경로 생성"""
    if target.kind == "profile":
        return f"/users/{_path_segment(target.owner)}"
    return f"/repos/{_path_segment(target.owner)}/{_path_segment(target.repository)}"


def _repository_parts(full_name: str) -> tuple[str, str]:
    """Repository full_name의 owner·name 분리"""
    parts = full_name.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("GitHub Repository full_name 형식이 올바르지 않습니다.")
    return parts[0], parts[1]


def _warning_from_error(source_url: str, error: GitHubCollectionError) -> GitHubCollectionWarning:
    """수집 오류의 경고 정보 변환"""
    return GitHubCollectionWarning(source_url=source_url, code=error.code, message=str(error))


def _collected_source(
    *,
    source_key: str,
    source_url: str,
    source_version: str | None,
    title: str,
    fields: list[tuple[str, str]],
    evidence_fields: list[tuple[str, str]] | None = None,
) -> CollectedSource:
    """필드 기반 Source·Evidence 후보 생성"""
    content_lines = [f"# {title}", ""]
    for field, value in fields:
        content_lines.append(f"- {field}: {value}")

    return CollectedSource(
        source_type="github",
        source_key=source_key,
        source_url=source_url,
        source_version=source_version,
        content="\n".join(content_lines),
        evidence_candidates=[
            EvidenceCandidate(snippet=value, locator=f"github.api.{field}")
            for field, value in evidence_fields or fields
        ],
    )


def _required_int(payload: Mapping[str, Any], field: str) -> int:
    """필수 양의 정수 필드 검증"""
    value = payload.get(field)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    raise ValueError(f"GitHub 응답의 {field}은 양의 정수여야 합니다.")


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    """필수 문자열 필드 검증"""
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"GitHub 응답의 {field}이 필요합니다.")
    return value


def _optional_text(payload: Mapping[str, Any], field: str) -> str | None:
    """선택 문자열 필드 검증"""
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"GitHub 응답의 {field}은 문자열이어야 합니다.")
    return value if value.strip() else None


def _optional_topics(payload: Mapping[str, Any]) -> list[str]:
    """선택 topic 문자열 목록 검증"""
    value = payload.get("topics")
    if value is None:
        return []
    valid_topics = isinstance(value, list) and all(
        isinstance(topic, str) and topic.strip() for topic in value
    )
    if not valid_topics:
        raise ValueError("GitHub 응답의 topics는 비어 있지 않은 문자열 목록이어야 합니다.")
    return value


def _parse_target(source_url: str) -> _GitHubTarget:
    """공개 GitHub URL 대상 파싱"""
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise GitHubCollectionError("unsupported_url", "GitHub 공개 URL만 수집할 수 있습니다.")
    if parsed.params or parsed.query or parsed.fragment:
        raise GitHubCollectionError("unsupported_url", "GitHub URL의 경로만 입력할 수 있습니다.")

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) == 1:
        return _GitHubTarget(kind="profile", owner=_nonempty_path_part(parts[0]))
    if len(parts) == 2:
        return _GitHubTarget(
            kind="repository",
            owner=_nonempty_path_part(parts[0]),
            repository=_nonempty_path_part(parts[1]),
        )
    raise GitHubCollectionError(
        "unsupported_url", "GitHub Profile 또는 Repository URL이 필요합니다."
    )


def _nonempty_path_part(value: str) -> str:
    """URL 경로 요소 검증"""
    if not value or value in {".", ".."}:
        raise GitHubCollectionError("unsupported_url", "GitHub URL 경로가 올바르지 않습니다.")
    return value


def _path_segment(value: str | None) -> str:
    """GitHub API 경로 세그먼트 인코딩"""
    if value is None:
        raise RuntimeError("Repository URL에는 저장소 이름이 필요합니다.")
    return quote(value, safe="-._~")


def _raise_for_status(response: httpx.Response) -> None:
    """GitHub HTTP 오류 코드 분류"""
    if response.status_code == 404:
        raise GitHubCollectionError(
            "not_found", "GitHub Profile 또는 Repository를 찾지 못했습니다."
        )
    if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
        raise GitHubCollectionError("rate_limited", "GitHub API 요청 한도에 도달했습니다.")
    if response.is_error:
        raise GitHubCollectionError("unavailable", "GitHub API 요청에 실패했습니다.")
