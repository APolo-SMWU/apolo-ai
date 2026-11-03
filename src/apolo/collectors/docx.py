"""Word(.docx) 문서의 본문·근거 후보 추출"""

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, replace
from typing import Literal

import docx
from docx.table import Table
from docx.text.hyperlink import Hyperlink
from docx.text.paragraph import Paragraph

from apolo.contracts.source import CollectedSource, EvidenceCandidate, EvidenceLayout

MAX_DOCX_BYTES = 10 * 1024 * 1024

MAX_DOCX_UNZIPPED_BYTES = 50 * 1024 * 1024
MAX_DOCX_MEMBERS = 1000
MAX_DOCX_TEXT_CHARS = 200_000
MAX_HEADING_CHARS = 40

_HEADING_STYLE = re.compile(r"^(?:heading|제목)\s*([1-9])$", re.IGNORECASE)


class DocxCollectionError(ValueError):
    """Word 본문 추출 오류 처리"""

    def __init__(self, code: Literal["too_large", "invalid_file", "no_text"], message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DocxText:
    """Word에서 읽은 문서 제목·본문·근거 후보. 본문 한 줄이 근거 후보 하나다"""

    title: str
    content: str
    evidence_candidates: list[EvidenceCandidate]


@dataclass(frozen=True)
class _Block:
    locator: str
    text: str
    heading: int | None = None
    layout: EvidenceLayout | None = None


def collect_docx_source(data: bytes, *, file_name: str, source_url: str) -> CollectedSource:
    """올린 Word 파일을 Source로 만든다. 같은 파일은 내용 해시가 같아 같은 Source가 된다"""
    text = extract_docx_text(data, file_name=file_name)
    return CollectedSource(
        source_type="file",
        source_key=f"file:docx:{hashlib.sha256(data).hexdigest()}",
        source_url=source_url,
        content=text.content,
        evidence_candidates=text.evidence_candidates,
    )


def extract_docx_text(data: bytes, *, file_name: str) -> DocxText:
    """제목 스타일로 섹션 경로를 만들고 문단·목록·표 행을 문서 순서대로 근거 후보로 만든다

    제목 스타일이 하나도 없으면 짧고 전체가 굵은 문단을 섹션 제목으로 본다.
    링크는 글자 뒤에 주소를 붙인다.
    """
    if len(data) > MAX_DOCX_BYTES:
        raise DocxCollectionError("too_large", "Word 파일은 10MB 이하만 읽을 수 있습니다.")
    _check_zip(data)
    try:
        document = docx.Document(io.BytesIO(data))
        return _document_text(document, file_name=file_name)
    except DocxCollectionError:
        raise
    except Exception as error:
        raise DocxCollectionError("invalid_file", "Word 파일을 열지 못했습니다.") from error


def _document_text(document, *, file_name: str) -> DocxText:
    title = (document.core_properties.title or "").strip()
    blocks: list[_Block] = []
    blank_before = False
    previous_space_after = 0.0
    bold_headings: set[str] = set()
    text_chars = 0
    for index, item in enumerate(document.iter_inner_content(), 1):
        if isinstance(item, Paragraph):
            text = _paragraph_text(item)
            if not text:
                blank_before = True
                continue
            paragraph_style = item.style
            style = paragraph_style.name if paragraph_style is not None else ""
            if style == "Title" and not title:
                title = text
                continue
            match = _HEADING_STYLE.match(style)
            is_list = _is_list(item, style)
            prefix = "• " if is_list else ""
            settings = _paragraph_settings(item, paragraph_style)
            indent, space_before = settings["left_indent"], settings["space_before"]
            space_after = settings["space_after"]
            if not is_list and len(text) <= MAX_HEADING_CHARS:
                runs = [run for run in item.runs if run.text.strip()]
                if runs and all(run.bold for run in runs):
                    bold_headings.add(f"docx.para:{index}")
            text_chars += len(text)
            if text_chars > MAX_DOCX_TEXT_CHARS:
                raise DocxCollectionError("too_large", "Word 파일 글자 수가 너무 많습니다.")
            blocks.append(
                _Block(
                    f"docx.para:{index}",
                    prefix + text,
                    int(match[1]) if match else None,
                    EvidenceLayout(
                        indent=indent.pt if indent is not None else None,
                        gap_before=max(
                            space_before.pt if space_before is not None else 0.0,
                            previous_space_after,
                        ),
                        blank_before=blank_before,
                        is_list=is_list,
                        keep_with_next=bool(settings["keep_with_next"]),
                    ),
                )
            )
            blank_before = False
            previous_space_after = space_after.pt if space_after is not None else 0.0
        elif isinstance(item, Table):
            previous_space_after = 0.0
            for row_index, row in enumerate(item.rows, 1):
                text = _row_text(row)
                if text:
                    text_chars += len(text)
                    if text_chars > MAX_DOCX_TEXT_CHARS:
                        raise DocxCollectionError("too_large", "Word 파일 글자 수가 너무 많습니다.")
                    blocks.append(
                        _Block(
                            f"docx.table:{index}:{row_index}",
                            text,
                            layout=EvidenceLayout(
                                table=f"docx.table:{index}", blank_before=blank_before
                            ),
                        )
                    )
                    blank_before = False

    if not any(block.text.strip() for block in blocks):
        raise DocxCollectionError("no_text", "Word 파일에서 글자를 찾지 못했습니다.")
    if all(block.heading is None for block in blocks):
        blocks = [
            replace(block, heading=1) if block.locator in bold_headings else block
            for block in blocks
        ]
        # 맨 앞 굵은 제목 바로 뒤가 또 제목이면 맨 앞 줄은 문서 이름이다
        if not title and len(blocks) > 1 and blocks[0].heading and blocks[1].heading:
            title = blocks.pop(0).text
    title = title or file_name

    content_lines = [f"# {title}"]
    candidates = [EvidenceCandidate(snippet=title, locator="docx.title")]
    section: list[tuple[int, str]] = []
    for block in blocks:
        if block.heading is not None:
            section = [(level, name) for level, name in section if level < block.heading]
            section.append((block.heading, block.text))
        path = " > ".join(name for _, name in section)
        suffix = f";section_path={path}" if path else ""
        if block.heading is not None:
            content_lines.append(f"{'#' * min(block.heading + 1, 6)} {block.text}")
        else:
            content_lines.append(
                f"[Word section path: {path}] {block.text}" if path else block.text
            )
        layout = (block.layout or EvidenceLayout()).model_copy(
            update={"heading_level": block.heading}
        )
        candidates.append(
            EvidenceCandidate(snippet=block.text, locator=block.locator + suffix, layout=layout)
        )

    content = "\n\n".join(content_lines)
    if len(content) > MAX_DOCX_TEXT_CHARS:
        raise DocxCollectionError("too_large", "Word 파일 글자 수가 너무 많습니다.")
    return DocxText(title=title, content=content, evidence_candidates=candidates)


def _check_zip(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
    except zipfile.BadZipFile as error:
        raise DocxCollectionError("invalid_file", "Word 파일을 열지 못했습니다.") from error
    if (
        len(members) > MAX_DOCX_MEMBERS
        or sum(member.file_size for member in members) > MAX_DOCX_UNZIPPED_BYTES
    ):
        raise DocxCollectionError("too_large", "Word 파일 내용이 너무 큽니다.")


def _paragraph_text(paragraph: Paragraph) -> str:
    parts: list[str] = []
    for item in paragraph.iter_inner_content():
        text = item.text
        if isinstance(item, Hyperlink):
            url = item.url
            if url.startswith(("http://", "https://")) and url not in text:
                text = f"{text} ({url})" if text.strip() else url
        parts.append(text)
    return " ".join("".join(parts).split())


def _cell_text(cell) -> str:
    parts = []
    for item in cell.iter_inner_content():
        if isinstance(item, Paragraph):
            parts.append(_paragraph_text(item))
        elif isinstance(item, Table):
            parts.extend(_row_text(row) for row in item.rows)
    return " ".join(part for part in parts if part)


def _row_text(row) -> str:
    # 값이 같은 별도 셀은 남기고, 같은 XML 셀을 참조하는 병합 셀만 중복을 없앤다.
    seen = set()
    parts = []
    for cell in row.cells:
        if cell._tc in seen:
            continue
        seen.add(cell._tc)
        text = _cell_text(cell)
        if text:
            parts.append(text)
    return " | ".join(parts)


def _is_list(paragraph: Paragraph, style: str) -> bool:
    properties = paragraph._p.pPr
    return (properties is not None and properties.numPr is not None) or style.startswith("List")


def _paragraph_settings(paragraph: Paragraph, style) -> dict:
    values = {
        name: getattr(paragraph.paragraph_format, name)
        for name in ("left_indent", "space_before", "space_after", "keep_with_next")
    }
    seen = set()
    while any(value is None for value in values.values()) and style is not None:
        if style.style_id in seen:
            break
        seen.add(style.style_id)
        formatting = style.paragraph_format
        values = {
            name: getattr(formatting, name) if value is None else value
            for name, value in values.items()
        }
        style = style.base_style
    return values
