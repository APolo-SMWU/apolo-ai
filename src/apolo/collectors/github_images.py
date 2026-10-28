"""GitHub Repository README의 대표 이미지 1장 조회"""

import os
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse

import httpx
from dotenv import load_dotenv

from apolo.collectors.github import GITHUB_API_URL, GITHUB_API_VERSION


async def readme_image(source_url: str, *, client: httpx.AsyncClient) -> str | None:
    """README HTML의 src는 첨부 이미지가 서명 주소(5분 유효)라 생성 직후 바로 받아야 한다"""
    parts = [part for part in urlparse(source_url).path.split("/") if part]
    if len(parts) != 2:
        return None
    owner, repository = parts
    readme_html = await _fetch_readme_html(client, owner, repository)
    if readme_html is None:
        return None
    parser = _ImageParser()
    parser.feed(readme_html)
    base = f"https://github.com/{owner}/{repository}/raw/HEAD/"
    for src, original in parser.images:
        url = urljoin(base, src)
        if is_representative_image(urljoin(base, original or src)):
            return url
    return None


def is_representative_image(url: str) -> bool:
    """배지·아바타·SVG는 대표 이미지가 아니다"""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    if parsed.scheme not in {"http", "https"} or not host:
        return False
    if host.endswith("shields.io") or "badge" in path:
        return False
    return host != "avatars.githubusercontent.com" and not path.endswith(".svg")


class _ImageParser(HTMLParser):
    """img의 다운로드 주소(src)와 필터용 원래 주소(data-canonical-src)"""

    def __init__(self) -> None:
        super().__init__()
        self.images: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        values = dict(attrs)
        src = values.get("src")
        if src:
            self.images.append((src, values.get("data-canonical-src")))


async def _fetch_readme_html(client: httpx.AsyncClient, owner: str, repository: str) -> str | None:
    load_dotenv()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github.html",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    path = f"/repos/{quote(owner, safe='-._~')}/{quote(repository, safe='-._~')}/readme"
    try:
        response = await client.get(f"{GITHUB_API_URL}{path}", headers=headers)
    except httpx.RequestError:
        return None
    return None if response.is_error else response.text
