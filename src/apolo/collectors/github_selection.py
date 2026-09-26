"""README가 부족한 GitHub Repository에서 Graph A 입력으로 쓸 원문을 규칙으로 고른다."""

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apolo.collectors.github import GitHubTreeEntry

MIN_README_TEXT_LENGTH = 300
# 프로필 목록에서 파일을 보충할 Repository 수. 직접 링크한 Repository는 항상 보충.
MAX_FILE_SELECTION_REPOSITORIES = 5
MAX_SELECTED_FILES = 3
MAX_SELECTED_FILE_BYTES = 100_000

# 배지·이미지·HTML 태그·URL은 프로젝트 설명이 아니므로 글자 수에서 뺀다. 링크는 글자만 남긴다.
_IMAGES_AND_TAGS = re.compile(
    r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)"  # 링크 걸린 배지 [![alt](img)](link)
    r"|!\[[^\]]*\]\([^)]*\)"  # 이미지 ![alt](img)
    r"|<[^>]+>"
)
_LINKS = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URLS = re.compile(r"https?://\S+")

# 기술 스택이 드러나는 의존성 파일. lock 파일은 목록에 없으므로 고르지 않는다.
_DEPENDENCY_FILES = frozenset(
    {
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "build.gradle",
        "build.gradle.kts",
        "pom.xml",
        "go.mod",
        "Cargo.toml",
        "Gemfile",
        "composer.json",
        "pubspec.yaml",
    }
)
# 프로젝트 설명과 무관한 문서
_IGNORED_DOCS = frozenset({"changelog.md", "license.md", "contributing.md", "code_of_conduct.md"})
_IGNORED_DIRECTORIES = frozenset(
    {"node_modules", "vendor", "dist", "build", "target", "venv", "__pycache__", "coverage"}
)


def is_readme_insufficient(readme: str | None) -> bool:
    """README가 없거나 설명 글자가 300자 미만이면 True. 공백은 세지 않는다."""
    if readme is None:
        return True
    text = _IMAGES_AND_TAGS.sub("", readme)
    text = _LINKS.sub(r"\1", text)
    text = _URLS.sub("", text)
    return sum(not character.isspace() for character in text) < MIN_README_TEXT_LENGTH


def select_repository_files(entries: Iterable["GitHubTreeEntry"]) -> list[str]:
    """의존성 파일, 문서 순으로 최대 3개 경로를 고른다. 같은 순위는 얕은 경로, 이름순."""
    candidates = []
    for entry in entries:
        if entry.kind != "file" or not entry.size or entry.size > MAX_SELECTED_FILE_BYTES:
            continue
        *directories, name = entry.path.split("/")
        if any(part.startswith(".") or part in _IGNORED_DIRECTORIES for part in directories):
            continue
        if name in _DEPENDENCY_FILES:
            priority = 0
        elif _is_project_doc(directories, name):
            priority = 1
        else:
            continue
        candidates.append((priority, len(directories), entry.path.lower(), entry.path))
    return [path for *_, path in sorted(candidates)[:MAX_SELECTED_FILES]]


def _is_project_doc(directories: list[str], name: str) -> bool:
    """최상위의 README 외 문서, docs 폴더 아래 문서, 하위 폴더 README인지 확인한다."""
    lowered = name.lower()
    if not lowered.endswith(".md") or lowered in _IGNORED_DOCS:
        return False
    if not directories:
        return lowered != "readme.md"
    return "docs" in directories or lowered == "readme.md"
