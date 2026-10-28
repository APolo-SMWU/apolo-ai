"""공개 Notion Page의 대표 이미지 1장 조회"""

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, urlencode, urlparse

import httpx

from apolo.collectors.github_images import is_representative_image
from apolo.collectors.notion import (
    NotionCollectionError,
    _block_plain_text,
    _block_type,
    _block_values_by_id,
    _heading_level,
    _root_page_block,
    _walk_descendant_blocks,
    fetch_public_notion_blocks,
)

NOTION_IMAGE_WIDTH = 800
# 상장·자격·자기소개 섹션 이미지는 프로젝트 대표 이미지가 아니다.
EXCLUDED_SECTION = re.compile(
    r"award|honor|certif|license|about|hello|profile|수상|상장|자격|소개|프로필", re.IGNORECASE
)


async def notion_page_image(source_url: str, *, client: httpx.AsyncClient) -> str | None:
    """업로드 이미지는 토큰 없는 공개 페이지 /image 프록시 주소로 반환"""
    try:
        fetched = await fetch_public_notion_blocks(source_url, client=client)
    except NotionCollectionError:
        return None
    block_values = _block_values_by_id(fetched.blocks)
    root_id, _root = _root_page_block(fetched.target, block_values)
    section_path: list[tuple[int, str]] = []
    for _block_id, block in _walk_descendant_blocks(root_id, block_values):
        block_type = _block_type(block)
        heading_level = _heading_level(block_type)
        if heading_level is not None:
            section_path = [(level, name) for level, name in section_path if level < heading_level]
            section_path.append((heading_level, _block_plain_text(block)))
            continue
        if block_type != "image":
            continue
        if any(EXCLUDED_SECTION.search(name) for _, name in section_path):
            continue
        url = _image_url(fetched.target.source_url, block)
        if url is not None and is_representative_image(url):
            return url
    return None


def _image_url(page_url: str, block: Mapping[str, Any]) -> str | None:
    properties = block.get("properties")
    source = properties.get("source") if isinstance(properties, Mapping) else None
    if not isinstance(source, list) or not source or not isinstance(source[0], list):
        return None
    value = source[0][0] if source[0] and isinstance(source[0][0], str) else ""
    if not (value.startswith("attachment:") or "prod-files-secure" in value):
        return value or None
    space_id, block_id = block.get("space_id"), block.get("id")
    if not isinstance(space_id, str) or not isinstance(block_id, str):
        return None
    query = urlencode(
        {"table": "block", "id": block_id, "spaceId": space_id, "width": NOTION_IMAGE_WIDTH}
    )
    return f"https://{urlparse(page_url).netloc}/image/{quote(value, safe='')}?{query}"
