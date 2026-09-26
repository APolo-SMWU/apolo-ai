"""GitHub·Public Notion 수집 결과를 공통 형식으로 모음"""

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from apolo.collectors.github import GitHubCollectionError, collect_github_sources
from apolo.collectors.notion import NotionCollectionError, collect_notion_sources
from apolo.contracts.source import CollectedSource


@dataclass(frozen=True)
class PublicCollectionWarning:
    """외부 소스의 부분 수집 실패 정보"""

    source_url: str
    code: str
    message: str


@dataclass(frozen=True)
class PublicCollectionResult:
    """외부 URL별 Source·경고 통합 결과"""

    sources: list[CollectedSource]
    warnings: list[PublicCollectionWarning]


async def collect_public_sources(
    source_urls: list[str], *, client: httpx.AsyncClient
) -> PublicCollectionResult:
    """URL별 Collector 실행 후 성공 결과와 경고를 순서대로 모음"""
    sources: list[CollectedSource] = []
    warnings: list[PublicCollectionWarning] = []

    for source_url in source_urls:
        try:
            hostname = urlparse(source_url).hostname or ""
        except ValueError:
            hostname = ""

        try:
            if hostname in {"github.com", "www.github.com"}:
                result = await collect_github_sources(source_url, client=client)
            elif hostname in {
                "notion.so",
                "www.notion.so",
                "notion.site",
                "www.notion.site",
            } or hostname.endswith(".notion.site"):
                result = await collect_notion_sources(source_url, client=client)
            else:
                warnings.append(
                    PublicCollectionWarning(
                        source_url=source_url,
                        code="unsupported_url",
                        message="GitHub 또는 Public Notion URL만 수집할 수 있습니다.",
                    )
                )
                continue
        except (GitHubCollectionError, NotionCollectionError) as error:
            warnings.append(
                PublicCollectionWarning(
                    source_url=source_url,
                    code=error.code,
                    message=str(error),
                )
            )
            continue

        sources.extend(result.sources)
        warnings.extend(
            PublicCollectionWarning(warning.source_url, warning.code, warning.message)
            for warning in result.warnings
        )

    return PublicCollectionResult(sources=sources, warnings=warnings)
