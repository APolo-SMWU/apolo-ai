"""Work 근거의 원본 문서에서 대표 이미지 1장을 GitHub > Notion 순서로 고른다"""

import asyncio
from uuid import UUID

import httpx

from apolo.collectors.github_images import readme_image
from apolo.collectors.notion_images import notion_page_image
from apolo.contracts.generate import GenerateResponse, WorkItem, WorksBlock
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.contracts.source import SourceDocument

MAX_CONCURRENT_IMAGE_LOOKUPS = 8


def work_document_ids(response: GenerateResponse, graph: ActiveKnowledgeGraph) -> list[UUID]:
    """Works 항목의 Entity·Fact 근거가 나온 원본 문서 ID"""
    by_entity = _document_ids_by_entity(graph)
    ids: list[UUID] = []
    for item in _work_items(response):
        for document_id in by_entity.get(item.entity_id, []):
            if document_id not in ids:
                ids.append(document_id)
    return ids


async def attach_work_images(
    response: GenerateResponse,
    graph: ActiveKnowledgeGraph,
    documents: list[SourceDocument],
    *,
    client: httpx.AsyncClient,
) -> None:
    """LLM이 고른 imageUrl은 쓰지 않는다. Notion은 GitHub에서 못 찾은 Work만 연다

    Notion은 여러 활동이 섞인 페이지의 사진이 붙지 않도록 Work 전용 페이지만 쓴다.
    """
    by_id = {document.id: document for document in documents}
    by_entity = _document_ids_by_entity(graph)
    pages = _referenced_notion_pages(graph)
    items = _work_items(response)
    sources = {
        item.entity_id: [
            by_id[i]
            for i in by_entity.get(item.entity_id, [])
            if i in by_id and _is_work_source(by_id[i], pages.get(item.entity_id, set()))
        ]
        for item in items
    }
    clear_work_images(response)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_IMAGE_LOOKUPS)
    for source_type, lookup in (("github", readme_image), ("notion", notion_page_image)):
        pending = [item for item in items if item.image_url is None]
        needed = {
            document.id: document
            for item in pending
            for document in sources[item.entity_id]
            if document.source_type == source_type
        }

        async def find(document: SourceDocument, lookup=lookup) -> str | None:
            async with semaphore:
                return await lookup(document.source_url, client=client)

        found = await asyncio.gather(*(find(document) for document in needed.values()))
        images = dict(zip(needed, found, strict=True))
        for item in pending:
            item.image_url = next(
                (
                    images[document.id]
                    for document in sources[item.entity_id]
                    if images.get(document.id)
                ),
                None,
            )


def clear_work_images(response: GenerateResponse) -> None:
    for item in _work_items(response):
        item.image_url = None


def _work_items(response: GenerateResponse) -> list[WorkItem]:
    return [
        item for block in response.blocks if isinstance(block, WorksBlock) for item in block.items
    ]


def _is_work_source(document: SourceDocument, referenced_pages: set[str]) -> bool:
    """Notion은 페이지 제목 블록이나 DB 속성이 이 Work의 근거일 때만 전용 페이지로 본다"""
    if document.source_type != "notion":
        return True
    return _page_id(document.source_key.removeprefix("notion:page:")) in referenced_pages


def _referenced_notion_pages(graph: ActiveKnowledgeGraph) -> dict[str, set[str]]:
    pages: dict[str, set[str]] = {}
    for entity_id, evidence in _evidence_by_entity(graph):
        ids = pages.setdefault(str(entity_id), set())
        for item in evidence:
            kind, _, rest = item.locator.partition(":")
            if kind in {"notion.block", "notion.property"}:
                ids.add(_page_id(rest.split(";")[0].split(":")[0]))
    return pages


def _page_id(value: str) -> str:
    return value.replace("-", "").lower()


def _evidence_by_entity(graph: ActiveKnowledgeGraph):
    yield from ((entity.id, entity.evidence) for entity in graph.entities)
    yield from ((fact.entity_id, fact.evidence) for fact in graph.facts)


def _document_ids_by_entity(graph: ActiveKnowledgeGraph) -> dict[str, list[UUID]]:
    by_entity: dict[str, list[UUID]] = {}
    for entity_id, evidence in _evidence_by_entity(graph):
        ids = by_entity.setdefault(str(entity_id), [])
        for item in evidence:
            if item.source_document_id not in ids:
                ids.append(item.source_document_id)
    return by_entity
