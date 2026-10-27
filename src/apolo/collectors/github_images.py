"""Works imageUrl의 GitHub user-attachments 주소를 서명 주소로 교체"""

import html
import os
import re
from collections.abc import Iterable
from urllib.parse import quote, urlparse

import httpx
from dotenv import load_dotenv

from apolo.collectors.github import GITHUB_API_URL, GITHUB_API_VERSION
from apolo.contracts.generate import GenerateResponse, ProjectLink, WorksBlock

# user-attachments 원래 주소는 비로그인 404라 README HTML의 서명 주소(5분 유효)를 쓴다.
USER_ATTACHMENT_PATTERN = re.compile(
    r"^https://github\.com/user-attachments/assets/([0-9a-fA-F-]{36})$"
)
SIGNED_IMAGE_PATTERN = re.compile(
    r'src="(https://private-user-images\.githubusercontent\.com/[^"]+)"'
)


async def sign_work_image_urls(response: GenerateResponse, *, client: httpx.AsyncClient) -> None:
    """서명 주소를 찾지 못하면 원래 주소를 그대로 둔다"""
    readmes: dict[tuple[str, str], str | None] = {}
    for block in response.blocks:
        if not isinstance(block, WorksBlock):
            continue
        for item in block.items:
            match = USER_ATTACHMENT_PATTERN.match(item.image_url or "")
            if match is None:
                continue
            for repository in _linked_repositories(item.links):
                if repository not in readmes:
                    readmes[repository] = await _fetch_readme_html(client, *repository)
                signed = _signed_url(readmes[repository], match.group(1))
                if signed is not None:
                    item.image_url = signed
                    break


def _linked_repositories(links: Iterable[ProjectLink]) -> list[tuple[str, str]]:
    repositories: list[tuple[str, str]] = []
    for link in links:
        parsed = urlparse(link.href)
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.hostname in {"github.com", "www.github.com"} and len(parts) >= 2:
            repository = (parts[0], parts[1])
            if repository not in repositories:
                repositories.append(repository)
    return repositories


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


def _signed_url(readme_html: str | None, asset_id: str) -> str | None:
    if readme_html is None:
        return None
    for match in SIGNED_IMAGE_PATTERN.finditer(readme_html):
        url = html.unescape(match.group(1))
        if asset_id.lower() in urlparse(url).path.lower():
            return url
    return None
