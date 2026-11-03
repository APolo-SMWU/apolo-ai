"""글자가 들어 있는 PDF의 본문·근거 후보 추출. 스캔 PDF(OCR)는 지원하지 않는다"""

import hashlib
import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Literal

import pdfplumber

from apolo.contracts.source import CollectedSource, EvidenceCandidate, EvidenceLayout

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 30
MAX_PDF_TEXT_CHARS = 200_000
# 본문보다 이만큼 크면 섹션 제목으로 본다
HEADING_SIZE_RATIO = 1.1
MAX_HEADING_CHARS = 40
# 글자가 깨졌는지 판단하는 읽을 수 있는 글자(한글·영문·숫자·문장부호) 비율
MIN_READABLE_RATIO = 0.6

_BULLET = re.compile(r"^[•·▪◦‣∙●○■□\-–*]\s*")
_READABLE = re.compile(r"[가-힣A-Za-z0-9\s.,:;()\[\]{}'\"/%&+\-–—·•@#!?~|<>「」『』]")

_PAGE_NUMBER = re.compile(r"(?i)(\bpage\s*)\d+|\d+(?=\s*(?:쪽|페이지))")
_BARE_PAGE_NUMBER = re.compile(r"^\s*\d{1,2}(?:\s*/\s*\d{1,2})?\s*$")


class PdfCollectionError(ValueError):
    """PDF 본문 추출 오류 처리"""

    def __init__(
        self, code: Literal["too_large", "invalid_file", "no_text", "unreadable"], message: str
    ) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PdfText:
    """PDF에서 읽은 문서 제목·본문·근거 후보. 본문 한 줄이 근거 후보 하나다"""

    title: str
    content: str
    evidence_candidates: list[EvidenceCandidate]


@dataclass
class _Line:
    page: int
    text: str
    size: float
    x0: float
    x1: float
    top: float
    bottom: float
    # 쪽 위·아래 끝 8% 안에 있는 줄인지
    margin: Literal["top", "bottom"] | None = None
    links: list[str] = field(default_factory=list)


def collect_pdf_source(data: bytes, *, file_name: str, source_url: str) -> CollectedSource:
    """올린 PDF를 Source로 만든다. 같은 파일은 내용 해시가 같아 같은 Source가 된다

    source_url은 원본 파일을 다시 찾을 수 있는 위치(예: 저장소 key)다.
    """
    text = extract_pdf_text(data, file_name=file_name)
    return CollectedSource(
        source_type="file",
        source_key=f"file:pdf:{hashlib.sha256(data).hexdigest()}",
        source_url=source_url,
        content=text.content,
        evidence_candidates=text.evidence_candidates,
    )


def extract_pdf_text(data: bytes, *, file_name: str) -> PdfText:
    """글자 크기로 섹션 제목을, 들여쓰기로 줄바꿈된 문장을 찾아 줄 단위 근거 후보로 만든다

    가장 큰 글자가 문서에 한 번만 나오면 섹션이 아니라 문서 제목(이름)으로 본다.
    여러 쪽 같은 위치에 반복되는 머리글·바닥글은 뺀다. 링크는 해당 줄 끝에 붙인다.
    """
    if len(data) > MAX_PDF_BYTES:
        raise PdfCollectionError("too_large", "PDF는 10MB 이하만 읽을 수 있습니다.")
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > MAX_PDF_PAGES:
                raise PdfCollectionError("too_large", "PDF는 30쪽 이하만 읽을 수 있습니다.")
            lines = []
            text_chars = 0
            for number, page in enumerate(pdf.pages, 1):
                try:
                    page_lines = _page_lines(number, page)
                    text_chars += sum(len(line.text) for line in page_lines)
                    if text_chars > MAX_PDF_TEXT_CHARS:
                        raise PdfCollectionError("too_large", "PDF 글자 수가 너무 많습니다.")
                    lines.extend(page_lines)
                finally:
                    # pdfplumber의 글자·배치 캐시를 페이지마다 해제한다.
                    page.close()
    except PdfCollectionError:
        raise
    except Exception as error:
        raise PdfCollectionError("invalid_file", "PDF 파일을 열지 못했습니다.") from error

    lines = _without_repeated_margins(lines)
    text = "".join(line.text for line in lines)
    if len(text.strip()) < 20:
        raise PdfCollectionError(
            "no_text", "PDF에서 글자를 찾지 못했습니다. 스캔 PDF일 수 있습니다."
        )
    if len(_READABLE.findall(text)) / len(text) < MIN_READABLE_RATIO:
        raise PdfCollectionError("unreadable", "PDF 글자가 깨져 있어 읽지 못했습니다.")

    headings = _heading_sizes(lines, _body_size(lines))
    heading_sizes = sorted(headings, reverse=True)
    title_lines = [line for line in lines if heading_sizes and line.size == heading_sizes[0]]
    title = file_name
    if len(title_lines) == 1:
        title = title_lines[0].text
        heading_sizes = heading_sizes[1:]
    level = {size: index for index, size in enumerate(heading_sizes)}

    title_text = _line_text(title_lines[0]) if len(title_lines) == 1 else title
    content_lines = [f"# {title_text}"]
    candidates = [EvidenceCandidate(snippet=title_text, locator="pdf.title")]
    section: list[tuple[int, str]] = []
    counters: Counter[int] = Counter()
    previous: _Line | None = None
    for line in _merge_wrapped(lines, headings):
        if len(title_lines) == 1 and line is title_lines[0]:
            continue
        counters[line.page] += 1
        locator = f"pdf.page:{line.page}:{counters[line.page]}"
        text = _line_text(line)
        layout = EvidenceLayout(
            page=line.page,
            indent=float(line.x0),
            gap_before=(
                float(line.top - previous.bottom)
                if previous is not None and previous.page == line.page
                else None
            ),
            font_size=float(line.size),
            heading_level=min(level[line.size] + 1, 9) if line.size in level else None,
            is_list=bool(_BULLET.match(line.text)),
        )
        previous = line
        if line.size in level:
            depth = level[line.size]
            section = [(d, name) for d, name in section if d < depth] + [(depth, line.text)]
            path = " > ".join(name for _, name in section)
            content_lines.append(f"{'#' * min(depth + 2, 6)} {text}")
            candidates.append(
                EvidenceCandidate(
                    snippet=text, locator=f"{locator};section_path={path}", layout=layout
                )
            )
            continue
        path = " > ".join(name for _, name in section)
        suffix = f";section_path={path}" if path else ""
        content_lines.append(f"[PDF section path: {path}] {text}" if path else text)
        candidates.append(
            EvidenceCandidate(snippet=text, locator=f"{locator}{suffix}", layout=layout)
        )

    content = "\n\n".join(content_lines)
    if len(content) > MAX_PDF_TEXT_CHARS:
        raise PdfCollectionError("too_large", "PDF 글자 수가 너무 많습니다.")
    return PdfText(title=title, content=content, evidence_candidates=candidates)


def _line_text(line: _Line) -> str:
    return line.text + "".join(f" (링크: {uri})" for uri in line.links)


def _page_lines(number: int, page: Any) -> list[_Line]:
    lines = []
    for raw in page.extract_text_lines():
        text = " ".join(raw["text"].split())
        if not text:
            continue
        # 글머리표 글자는 작게 찍히는 경우가 많아 크기 계산에서 뺀다
        sizes = [
            c["size"] for c in raw["chars"] if c["text"].strip() and not _BULLET.match(c["text"])
        ]
        size = round(median(sizes), 1) if sizes else 0.0
        margin = page.height * 0.08
        region = (
            "top"
            if raw["top"] < margin
            else "bottom"
            if raw["bottom"] > page.height - margin
            else None
        )
        lines.append(
            _Line(number, text, size, raw["x0"], raw["x1"], raw["top"], raw["bottom"], region)
        )
    for link in page.hyperlinks:
        uri = link.get("uri") or ""
        if not uri.startswith(("http://", "https://")):
            continue
        # 링크 글자가 가로로 들어 있는 줄 중 세로 중심이 가장 가까운 줄
        center = (link["top"] + link["bottom"]) / 2
        nearby = [
            line
            for line in lines
            if line.x0 - 3 <= link["x0"] <= line.x1 + 3
            and line.top - 3 <= center <= line.bottom + 3
        ]
        line = min(nearby, key=lambda c: abs((c.top + c.bottom) / 2 - center), default=None)
        if line is not None and uri not in line.links:
            line.links.append(uri)
    return lines


def _without_repeated_margins(lines: list[_Line]) -> list[_Line]:
    """여러 쪽 위·아래 끝에 똑같이 반복되는 줄(머리글·바닥글·쪽 번호 주소)을 뺀다"""
    pages = {line.page for line in lines}
    if len(pages) < 2:
        return lines
    repeated = defaultdict(set)
    for line in lines:
        if line.margin is not None:
            repeated[(line.margin, _margin_key(line))].add(line.page)
    threshold = max(2, (len(pages) + 1) // 2)
    return [
        line
        for line in lines
        if line.margin is None or len(repeated[(line.margin, _margin_key(line))]) < threshold
    ]


def _margin_key(line: _Line) -> str:
    # 연도·점수처럼 의미 있는 숫자는 보존하고, 쪽 번호 표기만 정규화한다.
    if _BARE_PAGE_NUMBER.fullmatch(line.text):
        return "page:0"
    return _PAGE_NUMBER.sub(lambda match: (match[1] or "") + "0", line.text)


def _body_size(lines: list[_Line]) -> float:
    """글자 수가 가장 많은 크기를 본문 크기로 본다"""
    weights: Counter[float] = Counter()
    for line in lines:
        weights[line.size] += len(line.text)
    return weights.most_common(1)[0][0]


def _heading_sizes(lines: list[_Line], body_size: float) -> set[float]:
    """본문보다 크고, 그 크기의 줄이 모두 짧고 글머리표가 아닌 글자 크기만 제목으로 본다"""
    by_size: dict[float, list[_Line]] = {}
    for line in lines:
        by_size.setdefault(line.size, []).append(line)
    return {
        size
        for size, group in by_size.items()
        if size >= body_size * HEADING_SIZE_RATIO
        and all(
            len(line.text) <= MAX_HEADING_CHARS and not _BULLET.match(line.text) for line in group
        )
    }


def _merge_wrapped(lines: list[_Line], headings: set[float]) -> list[_Line]:
    """앞 줄보다 더 들여쓰였고 글머리표로 시작하지 않는 바로 아래 줄은 앞 줄에 이어 붙인다"""
    merged: list[_Line] = []
    for line in lines:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.page == line.page
            and previous.size not in headings
            and line.size not in headings
            and not _BULLET.match(line.text)
            and line.x0 > previous.x0 + 3
            and 0 <= line.top - previous.bottom < line.size * 0.8
        ):
            previous.text = f"{previous.text} {line.text}"
            previous.bottom = line.bottom
            previous.links.extend(uri for uri in line.links if uri not in previous.links)
            continue
        merged.append(line)
    return merged
