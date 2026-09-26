"""Public Notion Page 공개 블록 수집·정규화"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

import httpx

from apolo.contracts.source import CollectedSource, EvidenceCandidate

NOTION_PAGE_ID_PATTERN = re.compile(
    r"(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$"
)
MAX_NOTION_BLOCK_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_NOTION_BLOCK_CHUNKS = 20
MAX_NOTION_SYNC_BATCHES = 20
MAX_NOTION_CHILD_PAGES = 20
MAX_NOTION_DATABASE_VIEWS = 20
MAX_NOTION_DATABASE_ROWS = 50
NOTION_SYNC_RECORDS_API_URL = "https://www.notion.so/api/v3/syncRecordValues"
NOTION_QUERY_COLLECTION_API_URL = "https://www.notion.so/api/v3/queryCollection"


class NotionCollectionError(ValueError):
    """Notion 공개 페이지 수집 오류 처리"""

    def __init__(
        self,
        code: Literal[
            "unsupported_url", "not_found", "inaccessible", "unavailable", "invalid_response"
        ],
        message: str,
    ) -> None:
        """수집 오류 코드·메시지 보관"""
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class NotionPageTarget:
    """공개 여부 확인 전의 Notion Page ID·URL"""

    page_id: str
    source_url: str

    @property
    def source_key(self) -> str:
        """Page ID 기반 Source 식별자"""
        return f"notion:page:{self.page_id}"


@dataclass(frozen=True)
class FetchedNotionBlocks:
    """공개 Notion Page에서 수집한 전체 블록 묶음"""

    target: NotionPageTarget
    blocks: Mapping[str, Mapping[str, Any]]
    space_id: str | None = None


@dataclass(frozen=True)
class NotionCollectionWarning:
    """하위 페이지 부분 수집 실패 경고 정보"""

    source_url: str
    code: str
    message: str


@dataclass(frozen=True)
class NotionCollectionResult:
    """부모·직접 하위 페이지 수집 결과"""

    sources: list[CollectedSource]
    warnings: list[NotionCollectionWarning]


@dataclass(frozen=True)
class _NotionBlockChunk:
    """한 번의 블록 응답·다음 cursor·space ID"""

    blocks: Mapping[str, Mapping[str, Any]]
    next_cursor: Mapping[str, Any] | None
    space_id: str | None


@dataclass(frozen=True)
class _NotionHttpResponse:
    """응답 스트림 종료 후 보존한 HTTP 상태·헤더·본문"""

    status_code: int
    headers: httpx.Headers
    content: bytes

    @property
    def is_redirect(self) -> bool:
        """HTTP 리다이렉트 여부"""
        return 300 <= self.status_code < 400

    @property
    def is_error(self) -> bool:
        """HTTP 오류 여부"""
        return self.status_code >= 400


@dataclass(frozen=True)
class _NotionDatabaseRows:
    """공개 데이터베이스 뷰의 항목·속성 스키마·추가 항목 여부"""

    rows: list[tuple[str, Mapping[str, Any]]]
    schema: Mapping[str, Mapping[str, Any]]
    has_more: bool


def parse_public_notion_url(source_url: str) -> NotionPageTarget:
    """지원하는 공개 Notion 주소인지 확인하고 Page ID 추출"""
    parsed = urlparse(source_url)
    hostname = parsed.hostname.lower() if parsed.hostname is not None else ""
    if parsed.scheme != "https" or not _is_notion_public_host(hostname):
        raise NotionCollectionError(
            "unsupported_url",
            "Public Notion Page URL만 수집할 수 있습니다.",
        )

    normalized_path = parsed.path.rstrip("/")
    page_id = _page_id_from_path(normalized_path)
    if page_id is None:
        raise NotionCollectionError("unsupported_url", "Notion Page ID가 포함된 URL이 필요합니다.")

    return NotionPageTarget(
        page_id=page_id,
        source_url=urlunparse(("https", hostname, normalized_path, "", "", "")),
    )


async def fetch_public_notion_blocks(
    source_url: str, *, client: httpx.AsyncClient
) -> FetchedNotionBlocks:
    """블록을 페이지별로 가져와 합친 뒤, 아직 받지 못한 자식 블록을 추가 수집"""
    target = parse_public_notion_url(source_url)
    blocks: dict[str, Mapping[str, Any]] = {}
    cursor: Mapping[str, Any] = {"stack": []}
    space_id: str | None = None

    for chunk_number in range(MAX_NOTION_BLOCK_CHUNKS):
        chunk = await _fetch_block_chunk(target, cursor, chunk_number, client=client)
        _merge_blocks(blocks, chunk.blocks)
        space_id = space_id or chunk.space_id
        if chunk.next_cursor is None:
            break
        cursor = chunk.next_cursor
    else:
        raise NotionCollectionError(
            "invalid_response", "Notion Page 블록 페이지네이션 제한을 초과했습니다."
        )

    await _fetch_missing_child_blocks(blocks, space_id, target.page_id, client=client)
    return FetchedNotionBlocks(target=target, blocks=blocks, space_id=space_id)


async def collect_notion_source(source_url: str, *, client: httpx.AsyncClient) -> CollectedSource:
    """Public Notion URL의 공통 Source 변환"""
    fetched = await fetch_public_notion_blocks(source_url, client=client)
    return normalize_notion_blocks(fetched.target, fetched.blocks)


async def collect_notion_sources(
    source_url: str, *, client: httpx.AsyncClient
) -> NotionCollectionResult:
    """부모·직접 하위 페이지·공개 데이터베이스 항목 수집"""
    fetched = await fetch_public_notion_blocks(source_url, client=client)
    parent = normalize_notion_blocks(fetched.target, fetched.blocks)
    child_page_ids = _direct_child_page_ids(fetched.target, fetched.blocks)
    sources = [parent]
    fetched_pages = [fetched]
    warnings: list[NotionCollectionWarning] = []

    if len(child_page_ids) > MAX_NOTION_CHILD_PAGES:
        warnings.append(
            NotionCollectionWarning(
                source_url=parent.source_url,
                code="subpage_limit",
                message=f"직접 하위 페이지 {MAX_NOTION_CHILD_PAGES}개만 수집했습니다.",
            )
        )

    for child_id in child_page_ids[:MAX_NOTION_CHILD_PAGES]:
        child_url = f"https://{urlparse(parent.source_url).netloc}/{child_id}"
        try:
            child = await fetch_public_notion_blocks(child_url, client=client)
            sources.append(normalize_notion_blocks(child.target, child.blocks))
            fetched_pages.append(child)
        except NotionCollectionError as error:
            warnings.append(
                NotionCollectionWarning(
                    source_url=child_url,
                    code=error.code,
                    message=str(error),
                )
            )

    database_sources, database_warnings = await _collect_database_sources(
        fetched_pages, client=client
    )
    sources.extend(database_sources)
    warnings.extend(database_warnings)
    return NotionCollectionResult(sources=sources, warnings=warnings)


def normalize_notion_blocks(
    target: NotionPageTarget, blocks: Mapping[str, Mapping[str, Any]]
) -> CollectedSource:
    """전체 블록의 제목·텍스트를 Source·Evidence 후보로 변환"""
    block_values = _block_values_by_id(blocks)
    root_id, root = _root_page_block(target, block_values)
    title = _block_plain_text(root) or "Untitled Notion Page"

    lines = [f"# {title}"]
    evidence_candidates = [EvidenceCandidate(snippet=title, locator=f"notion.block:{root_id}")]
    for block_id, block in _walk_descendant_blocks(root_id, block_values):
        text = _block_plain_text(block)
        if not text:
            continue
        line = _format_block_line(_block_type(block), text, block)
        if line is None:
            continue
        lines.append(line)
        evidence_candidates.append(
            EvidenceCandidate(snippet=text, locator=f"notion.block:{block_id}")
        )

    return CollectedSource(
        source_type="notion",
        source_key=target.source_key,
        source_url=target.source_url,
        source_version=_source_version(root),
        content="\n\n".join(lines),
        evidence_candidates=evidence_candidates,
    )


async def _collect_database_sources(
    pages: list[FetchedNotionBlocks], *, client: httpx.AsyncClient
) -> tuple[list[CollectedSource], list[NotionCollectionWarning]]:
    """공개 데이터베이스 뷰의 항목을 별도 Source로 수집"""
    sources: list[CollectedSource] = []
    warnings: list[NotionCollectionWarning] = []
    seen_views: set[str] = set()
    seen_pages = {page.target.page_id for page in pages}
    attempted_rows = 0

    for page in pages:
        for view_id, view_block in _direct_collection_views(page):
            if view_id in seen_views:
                continue
            if len(seen_views) >= MAX_NOTION_DATABASE_VIEWS:
                warnings.append(
                    NotionCollectionWarning(
                        page.target.source_url,
                        "database_view_limit",
                        "데이터베이스 뷰 수집 제한을 초과했습니다.",
                    )
                )
                return sources, warnings
            seen_views.add(view_id)
            try:
                rows = await _fetch_collection_rows(
                    view_id, view_block, page.space_id, client=client
                )
            except NotionCollectionError as error:
                warnings.append(
                    NotionCollectionWarning(page.target.source_url, error.code, str(error))
                )
                continue

            if rows.has_more:
                warnings.append(
                    NotionCollectionWarning(
                        page.target.source_url,
                        "database_partial",
                        "데이터베이스 뷰에 추가 항목이 있습니다.",
                    )
                )

            for row_id, row_block in rows.rows:
                if row_id in seen_pages:
                    continue
                if attempted_rows >= MAX_NOTION_DATABASE_ROWS:
                    warnings.append(
                        NotionCollectionWarning(
                            page.target.source_url,
                            "database_row_limit",
                            "데이터베이스 항목 수집 제한을 초과했습니다.",
                        )
                    )
                    return sources, warnings
                seen_pages.add(row_id)
                attempted_rows += 1
                row_url = f"https://{urlparse(page.target.source_url).netloc}/{row_id}"
                try:
                    fetched_row = await fetch_public_notion_blocks(row_url, client=client)
                    source = normalize_notion_blocks(fetched_row.target, fetched_row.blocks)
                    sources.append(_source_with_database_properties(source, row_block, rows.schema))
                except NotionCollectionError as error:
                    warnings.append(NotionCollectionWarning(row_url, error.code, str(error)))

    return sources, warnings


def _direct_collection_views(
    page: FetchedNotionBlocks,
) -> list[tuple[str, Mapping[str, Any]]]:
    """페이지 내부 데이터베이스 뷰 ID·블록 탐색"""
    values = _block_values_by_id(page.blocks)
    root_id, _ = _root_page_block(page.target, values)
    views: list[tuple[str, Mapping[str, Any]]] = []
    for _, block in _walk_descendant_blocks(root_id, values):
        if _block_type(block) != "collection_view":
            continue
        view_ids = block.get("view_ids")
        if isinstance(view_ids, list):
            views.extend((view_id, block) for view_id in view_ids if isinstance(view_id, str))
    return views


async def _fetch_collection_rows(
    view_id: str,
    view_block: Mapping[str, Any],
    space_id: str | None,
    *,
    client: httpx.AsyncClient,
) -> _NotionDatabaseRows:
    """공개 뷰의 항목·컬렉션 속성 스키마 조회"""
    if space_id is None:
        raise NotionCollectionError("invalid_response", "Notion space ID가 없습니다.")
    response = await _post_json_response(
        client,
        NOTION_SYNC_RECORDS_API_URL,
        {
            "requests": [
                {
                    "pointer": {"table": "collection_view", "id": view_id, "spaceId": space_id},
                    "version": -1,
                }
            ]
        },
    )
    _raise_for_block_status(response)
    view = _record_value(_decode_json(response), "collection_view", view_id)
    response = await _post_json_response(
        client,
        NOTION_QUERY_COLLECTION_API_URL,
        {
            "collectionView": view,
            "collectionViewBlock": view_block,
            "clientType": "notion_app",
            "userTimeZone": "Asia/Seoul",
            "isFullScreen": False,
            "isMobile": False,
        },
    )
    _raise_for_block_status(response)
    payload = _decode_json(response)
    result = payload.get("result")
    reducers = result.get("reducerResults") if isinstance(result, Mapping) else None
    groups = (
        [
            value
            for value in reducers.values()
            if isinstance(value, Mapping) and value.get("type") == "results"
        ]
        if isinstance(reducers, Mapping)
        else []
    )
    if not groups:
        raise NotionCollectionError(
            "invalid_response", "데이터베이스 항목 목록이 올바르지 않습니다."
        )
    block_ids: list[str] = []
    has_more = False
    for group in groups:
        ids = group.get("blockIds")
        more = group.get("hasMore")
        if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
            raise NotionCollectionError(
                "invalid_response", "데이터베이스 항목 목록이 올바르지 않습니다."
            )
        if not isinstance(more, bool):
            raise NotionCollectionError(
                "invalid_response", "데이터베이스 추가 항목 상태가 없습니다."
            )
        block_ids.extend(ids)
        has_more = has_more or more
    block_ids = list(dict.fromkeys(block_ids))

    collection_id = view_block.get("collection_id")
    if not isinstance(collection_id, str):
        raise NotionCollectionError("invalid_response", "데이터베이스 ID가 없습니다.")
    collection = _record_value(payload, "collection", collection_id)
    schema = collection.get("schema")
    if not isinstance(schema, Mapping):
        raise NotionCollectionError("invalid_response", "데이터베이스 속성 스키마가 없습니다.")
    rows = [
        (_normalized_block_id(item), _record_value(payload, "block", item)) for item in block_ids
    ]
    return _NotionDatabaseRows(rows=rows, schema=schema, has_more=has_more)


def _record_value(payload: Mapping[str, Any], table: str, record_id: str) -> Mapping[str, Any]:
    """recordMap 항목의 블록·뷰·컬렉션 값 추출"""
    record_map = payload.get("recordMap")
    records = record_map.get(table) if isinstance(record_map, Mapping) else None
    record = records.get(record_id) if isinstance(records, Mapping) else None
    envelope = record.get("value") if isinstance(record, Mapping) else None
    value = envelope.get("value") if isinstance(envelope, Mapping) else None
    if not isinstance(value, Mapping):
        raise NotionCollectionError("invalid_response", f"Notion {table} 항목을 읽을 수 없습니다.")
    return value


def _source_with_database_properties(
    source: CollectedSource,
    row: Mapping[str, Any],
    schema: Mapping[str, Mapping[str, Any]],
) -> CollectedSource:
    """데이터베이스 속성 원문을 항목 Source·Evidence에 추가"""
    properties = row.get("properties")
    if not isinstance(properties, Mapping):
        return source
    lines: list[str] = []
    evidence = list(source.evidence_candidates)
    for property_id, definition in schema.items():
        if property_id == "title" or not isinstance(definition, Mapping):
            continue
        name = definition.get("name")
        if not isinstance(name, str) or not name:
            continue
        value = _database_property_text(properties.get(property_id), definition.get("type"))
        if value is None:
            continue
        lines.append(f"- {name}: {value}")
        locator = f"notion.property:{source.source_key.removeprefix('notion:page:')}:{property_id}"
        dates = (
            _database_date_values(properties.get(property_id))
            if definition.get("type") == "date"
            else None
        )
        snippets = [part for part in dates if part is not None] if dates else [value]
        evidence.extend(EvidenceCandidate(snippet=part, locator=locator) for part in snippets)
    if not lines:
        return source
    return source.model_copy(
        update={
            "content": f"{source.content}\n\n## Database properties\n\n" + "\n".join(lines),
            "evidence_candidates": evidence,
        }
    )


def _database_property_text(value: object, property_type: object) -> str | None:
    """Notion 속성의 텍스트·날짜 값 추출"""
    if not isinstance(value, list):
        return None
    if property_type == "date":
        dates = _database_date_values(value)
        if dates is None:
            return None
        start, end = dates
        return f"{start} ~ {end}" if end is not None else start
    parts = [
        fragment[0]
        for fragment in value
        if isinstance(fragment, list) and fragment and isinstance(fragment[0], str)
    ]
    text = "".join(parts).strip()
    return text or None


def _database_date_values(value: object) -> tuple[str, str | None] | None:
    """Notion 날짜 속성의 원본 시작일·종료일 추출"""
    if not isinstance(value, list):
        return None
    for fragment in value:
        if not isinstance(fragment, list) or len(fragment) < 2:
            continue
        for annotation in fragment[1] if isinstance(fragment[1], list) else []:
            if not isinstance(annotation, list) or len(annotation) < 2 or annotation[0] != "d":
                continue
            date = annotation[1]
            if isinstance(date, Mapping) and isinstance(date.get("start_date"), str):
                end = date.get("end_date")
                return date["start_date"], end if isinstance(end, str) else None
    return None


async def _fetch_block_chunk(
    target: NotionPageTarget,
    cursor: Mapping[str, Any],
    chunk_number: int,
    *,
    client: httpx.AsyncClient,
) -> _NotionBlockChunk:
    """공개 Page API의 블록 한 묶음 요청·검증"""
    response = await _post_json_response(
        client,
        _public_page_api_url(target),
        {
            "page": {"id": _page_uuid(target.page_id)},
            "limit": 100,
            "cursor": cursor,
            "chunkNumber": chunk_number,
            "verticalColumns": False,
        },
    )
    _raise_for_block_status(response)
    payload = _decode_json(response)
    return _NotionBlockChunk(
        blocks=_record_map_blocks(payload),
        next_cursor=_next_cursor(payload),
        space_id=_space_id(payload),
    )


async def _fetch_missing_child_blocks(
    blocks: dict[str, Mapping[str, Any]],
    space_id: str | None,
    root_id: str,
    *,
    client: httpx.AsyncClient,
) -> None:
    """지연 로드된 자식 블록의 추가 수집"""
    if space_id is None:
        return

    for _ in range(MAX_NOTION_SYNC_BATCHES):
        missing_ids = _missing_child_block_ids(blocks, root_id)
        if not missing_ids:
            return

        found_new_block = False
        for batch_start in range(0, len(missing_ids), 100):
            batch_ids = missing_ids[batch_start : batch_start + 100]
            response = await _post_json_response(
                client,
                NOTION_SYNC_RECORDS_API_URL,
                {
                    "requests": [
                        {
                            "pointer": {"table": "block", "id": block_id, "spaceId": space_id},
                            "version": -1,
                        }
                        for block_id in batch_ids
                    ]
                },
            )
            _raise_for_block_status(response)
            returned_blocks = _record_map_blocks(_decode_json(response))
            known_count = len(blocks)
            _merge_blocks(blocks, returned_blocks)
            found_new_block = found_new_block or len(blocks) > known_count

        if not found_new_block:
            return

    raise NotionCollectionError(
        "invalid_response", "Notion Page 자식 블록 보충 제한을 초과했습니다."
    )


def _is_notion_public_host(hostname: str) -> bool:
    """지원하는 Notion 공개 페이지 호스트 여부"""
    known_hosts = {"notion.so", "www.notion.so", "notion.site", "www.notion.site"}
    return hostname in known_hosts or hostname.endswith(".notion.site")


def _page_id_from_path(path: str) -> str | None:
    """URL 경로 끝의 Notion Page ID 추출"""
    match = NOTION_PAGE_ID_PATTERN.search(path)
    if match is None:
        return None
    return match.group().replace("-", "").lower()


async def _post_json_response(
    client: httpx.AsyncClient, url: str, body: Mapping[str, object]
) -> _NotionHttpResponse:
    """응답 크기 제한을 적용한 JSON POST 요청"""
    try:
        async with client.stream("POST", url, json=body, follow_redirects=False) as response:
            if response.is_redirect or response.is_error:
                return _NotionHttpResponse(response.status_code, response.headers, b"")

            content_length = response.headers.get("content-length")
            if content_length is not None and _content_length_exceeds_limit(
                content_length, MAX_NOTION_BLOCK_RESPONSE_BYTES
            ):
                raise NotionCollectionError(
                    "invalid_response", "Notion Page 블록 응답 크기가 수집 제한을 초과했습니다."
                )

            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > MAX_NOTION_BLOCK_RESPONSE_BYTES:
                    raise NotionCollectionError(
                        "invalid_response", "Notion Page 블록 응답 크기가 수집 제한을 초과했습니다."
                    )
            return _NotionHttpResponse(response.status_code, response.headers, bytes(content))
    except httpx.RequestError as error:
        raise NotionCollectionError(
            "unavailable", "Notion Page 블록 정보에 연결하지 못했습니다."
        ) from error


def _public_page_api_url(target: NotionPageTarget) -> str:
    """공개 페이지 호스트의 블록 API URL"""
    parsed = urlparse(target.source_url)
    return urlunparse(("https", parsed.netloc, "/api/v3/loadCachedPageChunkV2", "", "", ""))


def _page_uuid(page_id: str) -> str:
    """32자리 Page ID의 UUID 형식 변환"""
    return f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"


def _content_length_exceeds_limit(content_length: str, limit: int) -> bool:
    """Content-Length의 응답 크기 초과 여부"""
    try:
        return int(content_length) > limit
    except ValueError:
        return False


def _raise_for_block_status(response: _NotionHttpResponse) -> None:
    """블록 응답 상태의 수집 오류 변환"""
    if response.status_code == 404:
        raise NotionCollectionError("not_found", "Notion Page를 찾지 못했습니다.")
    if 400 <= response.status_code < 500:
        raise NotionCollectionError("inaccessible", "Notion Page 블록 정보에 접근할 수 없습니다.")
    if response.is_error or response.is_redirect:
        raise NotionCollectionError("unavailable", "Notion Page 블록 요청에 실패했습니다.")


def _decode_json(response: _NotionHttpResponse) -> Mapping[str, Any]:
    """JSON Content-Type·본문 형식 검증"""
    content_type = response.headers.get("content-type", "")
    if not content_type.lower().startswith("application/json"):
        raise NotionCollectionError("invalid_response", "Notion Page 블록 응답이 JSON이 아닙니다.")
    try:
        payload = json.loads(response.content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NotionCollectionError(
            "invalid_response", "Notion Page 블록 JSON을 읽을 수 없습니다."
        ) from error
    if not isinstance(payload, Mapping):
        raise NotionCollectionError(
            "invalid_response", "Notion Page 블록 응답 형식이 올바르지 않습니다."
        )
    return payload


def _record_map_blocks(payload: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    """recordMap의 블록 목록 추출·검증"""
    record_map = payload.get("recordMap")
    if not isinstance(record_map, Mapping):
        raise NotionCollectionError("invalid_response", "Notion Page recordMap이 없습니다.")
    blocks = record_map.get("block")
    valid_blocks = isinstance(blocks, Mapping) and all(
        isinstance(block_id, str) and isinstance(block, Mapping)
        for block_id, block in blocks.items()
    )
    if not valid_blocks:
        raise NotionCollectionError(
            "invalid_response", "Notion Page block 목록 형식이 올바르지 않습니다."
        )
    return blocks


def _next_cursor(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """다음 블록 묶음의 cursor 추출·검증"""
    cursors = payload.get("cursors", [])
    if not isinstance(cursors, list):
        raise NotionCollectionError(
            "invalid_response", "Notion Page cursor 형식이 올바르지 않습니다."
        )
    if not cursors:
        return None
    cursor = cursors[0]
    stack = cursor.get("stack") if isinstance(cursor, Mapping) else None
    if not isinstance(stack, list):
        raise NotionCollectionError(
            "invalid_response", "Notion Page 다음 cursor가 올바르지 않습니다."
        )
    return {"stack": stack} if stack else None


def _space_id(payload: Mapping[str, Any]) -> str | None:
    """자식 블록 요청에 필요한 space ID 추출"""
    space_id = payload.get("spaceId")
    if isinstance(space_id, str) and space_id:
        return space_id
    return None


def _merge_blocks(
    destination: dict[str, Mapping[str, Any]], incoming: Mapping[str, Mapping[str, Any]]
) -> None:
    """새 블록 묶음을 전체 블록 목록에 병합"""
    destination.update(incoming)


def _missing_child_block_ids(blocks: Mapping[str, Mapping[str, Any]], root_id: str) -> list[str]:
    """요청한 페이지 내부의 누락된 자식 블록 ID 탐색"""
    block_values = _block_values_by_id(blocks)
    missing_ids: list[str] = []
    seen: set[str] = set()
    pending = [root_id]
    while pending:
        current_id = _normalized_block_id(pending.pop())
        if current_id in seen:
            continue
        seen.add(current_id)
        entry = block_values.get(current_id)
        if entry is None:
            continue
        _, block = entry
        if current_id != _normalized_block_id(root_id) and _block_type(block) == "page":
            continue
        children = block.get("content")
        if not isinstance(children, list):
            continue
        for child_id in reversed(children):
            if not isinstance(child_id, str):
                continue
            normalized_id = _normalized_block_id(child_id)
            if normalized_id in block_values:
                pending.append(child_id)
                continue
            if normalized_id in seen:
                continue
            seen.add(normalized_id)
            missing_ids.append(child_id)
    return missing_ids


def _block_values_by_id(
    blocks: Mapping[str, Mapping[str, Any]],
) -> dict[str, tuple[str, Mapping[str, Any]]]:
    """recordMap 블록 값을 정규화 ID로 색인"""
    values: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for record in blocks.values():
        envelope = record.get("value")
        block = envelope.get("value") if isinstance(envelope, Mapping) else None
        block_id = block.get("id") if isinstance(block, Mapping) else None
        if not isinstance(block_id, str) or not block_id:
            continue
        values[_normalized_block_id(block_id)] = (block_id, block)
    return values


def _root_page_block(
    target: NotionPageTarget,
    block_values: Mapping[str, tuple[str, Mapping[str, Any]]],
) -> tuple[str, Mapping[str, Any]]:
    """최상위 Page 블록 조회·검증"""
    root = block_values.get(target.page_id)
    if root is None or _block_type(root[1]) != "page":
        raise NotionCollectionError(
            "invalid_response", "Notion Page 최상위 블록을 찾을 수 없습니다."
        )
    return root


def _direct_child_page_ids(
    target: NotionPageTarget, blocks: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    """부모 페이지 내부의 직접 하위 페이지 ID 탐색"""
    block_values = _block_values_by_id(blocks)
    root_id, _ = _root_page_block(target, block_values)
    return [
        _normalized_block_id(block_id)
        for block_id, block in _walk_descendant_blocks(root_id, block_values)
        if _block_type(block) == "page"
    ]


def _walk_descendant_blocks(
    root_id: str, block_values: Mapping[str, tuple[str, Mapping[str, Any]]]
) -> list[tuple[str, Mapping[str, Any]]]:
    """content ID 순서에 따른 하위 블록 순회"""
    ordered_blocks: list[tuple[str, Mapping[str, Any]]] = []
    visited = {_normalized_block_id(root_id)}

    def visit(block_id: str) -> None:
        """자식 블록의 재귀 방문·중복 방지"""
        normalized_id = _normalized_block_id(block_id)
        if normalized_id in visited:
            return
        entry = block_values.get(normalized_id)
        if entry is None:
            return
        visited.add(normalized_id)
        canonical_id, block = entry
        ordered_blocks.append((canonical_id, block))
        if _block_type(block) == "page":
            return
        children = block.get("content")
        if isinstance(children, list):
            for child_id in children:
                if isinstance(child_id, str):
                    visit(child_id)

    root = block_values.get(_normalized_block_id(root_id))
    if root is not None:
        children = root[1].get("content")
        if isinstance(children, list):
            for child_id in children:
                if isinstance(child_id, str):
                    visit(child_id)
    return ordered_blocks


def _normalized_block_id(block_id: str) -> str:
    """하이픈 없는 소문자 블록 ID"""
    return block_id.replace("-", "").lower()


def _block_type(block: Mapping[str, Any]) -> str:
    """블록 유형 문자열 추출"""
    value = block.get("type")
    return value if isinstance(value, str) else ""


def _block_plain_text(block: Mapping[str, Any]) -> str:
    """블록 title 조각의 일반 텍스트 결합"""
    properties = block.get("properties")
    title = properties.get("title") if isinstance(properties, Mapping) else None
    if not isinstance(title, list):
        return ""

    parts: list[str] = []
    for fragment in title:
        if isinstance(fragment, list) and fragment and isinstance(fragment[0], str):
            parts.append(fragment[0])
    return "".join(parts).strip()


def _format_block_line(block_type: str, text: str, block: Mapping[str, Any]) -> str | None:
    """지원하는 텍스트 블록의 Markdown 형식 변환"""
    if block_type == "header":
        return f"## {text}"
    if block_type == "sub_header":
        return f"### {text}"
    if block_type == "sub_sub_header":
        return f"#### {text}"
    if block_type == "bulleted_list":
        return f"- {text}"
    if block_type == "numbered_list":
        return f"1. {text}"
    if block_type == "to_do":
        return f"- [{'x' if _todo_is_checked(block) else ' '}] {text}"
    if block_type == "quote":
        return f"> {text}"
    if block_type == "toggle":
        return f"▸ {text}"
    if block_type == "code":
        return f"```\n{text}\n```"
    if block_type in {"text", "callout"}:
        return text
    return None


def _todo_is_checked(block: Mapping[str, Any]) -> bool:
    """할 일 블록의 완료 표시 여부"""
    properties = block.get("properties")
    checked = properties.get("checked") if isinstance(properties, Mapping) else None
    if isinstance(checked, bool):
        return checked
    if isinstance(checked, list) and checked:
        first_value = checked[0]
        return isinstance(first_value, list) and bool(first_value) and first_value[0] == "Yes"
    return False


def _source_version(root: Mapping[str, Any]) -> str | None:
    """최상위 블록의 마지막 수정 시각 추출"""
    value = root.get("last_edited_time")
    return str(value) if isinstance(value, int) and not isinstance(value, bool) else None
