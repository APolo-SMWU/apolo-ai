"""파일의 배치 단서를 이용해 항목을 유지하고, 불확실한 경계에는 원문 문맥을 겹친다."""

from apolo.contracts.source import CollectedSource, EvidenceCandidate

FILE_CHUNK_CANDIDATES = 30
FILE_CHUNK_OVERLAP = 5
_TITLES = {"pdf.title", "docx.title"}


def split_file_source(source: CollectedSource, segments: list[str]) -> list[CollectedSource]:
    candidates = source.evidence_candidates
    shared = [i for i, candidate in enumerate(candidates) if candidate.locator in _TITLES]
    items: list[list[int]] = []
    for index, candidate in enumerate(candidates):
        if index in shared:
            continue
        previous = candidates[items[-1][-1]] if items else None
        if previous is None or _starts_item(previous, candidate):
            items.append([index])
        else:
            items[-1].append(index)

    groups: list[list[int]] = []
    item_start = {}
    for item in items:
        item_start.update(dict.fromkeys(item, item[0]))
        # 한 조각에 들어가는 항목은 유지하고, 상한을 넘는 항목만 나눈다.
        for start in range(0, len(item), FILE_CHUNK_CANDIDATES):
            part = item[start : start + FILE_CHUNK_CANDIDATES]
            if groups and len(groups[-1]) + len(part) <= FILE_CHUNK_CANDIDATES:
                groups[-1].extend(part)
            else:
                groups.append(part)
    if len(groups) < 2:
        return [source]

    headings: list[tuple[int, int]] = []
    parents: dict[int, list[int]] = {}
    for index, candidate in enumerate(candidates):
        level = candidate.layout.heading_level if candidate.layout is not None else None
        if level is not None:
            headings = [(depth, i) for depth, i in headings if depth < level]
            headings.append((level, index))
        parents[index] = [i for _, i in headings]

    chunks = []
    for number, group in enumerate(groups):
        first = group[0]
        context = set(parents[first])
        layout = candidates[first].layout
        clear_boundary = first == item_start[first] and (
            layout is not None and layout.heading_level is not None
        )
        if number and not clear_boundary:
            context.update(groups[number - 1][-FILE_CHUNK_OVERLAP:])
        if item_start[first] < first:
            context.add(item_start[first])
        context.difference_update(group)
        context.difference_update(shared)
        indexes = sorted(set(shared) | context | set(group))
        chunks.append(
            source.model_copy(
                update={
                    "content": "\n\n".join(segments[i] for i in indexes),
                    "evidence_candidates": [candidates[i] for i in indexes],
                    "context_evidence_refs": [candidates[i].locator for i in sorted(context)],
                }
            )
        )
    return chunks


def _starts_item(previous: EvidenceCandidate, current: EvidenceCandidate) -> bool:
    left, right = previous.layout, current.layout
    if right is None:
        return False
    if left is not None and left.keep_with_next:
        return False
    if right.heading_level is not None:
        # 섹션 제목 직후의 하위 항목 제목은 본문과 함께 취급한다.
        return not (
            left is not None
            and left.heading_level is not None
            and left.heading_level < right.heading_level
        )
    if left is not None and left.heading_level is not None:
        return False
    if right.table is not None:
        return left is None or left.table != right.table
    if left is not None and left.table is not None:
        return True
    if right.is_list:
        return False
    if right.blank_before:
        return True
    gap = right.gap_before
    if gap is None:
        return False
    if right.page is None:
        return gap >= 12.0
    # PDF의 페이지 경계 자체는 항목 경계로 보지 않는다.
    if left is None or right.page != left.page:
        return False
    return gap >= max(12.0, (right.font_size or 10.0) * 1.2) or (
        left.indent is not None
        and right.indent is not None
        and left.indent - right.indent >= 6
        and gap >= 6
    )
