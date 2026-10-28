"""긴 Notion Source를 최상위 섹션 단위 조각으로 나눠 추출하고 결과를 하나로 합친다"""

import re

from apolo.contracts.extraction import SELF_REF, ExtractionResult
from apolo.contracts.source import CollectedSource, EvidenceCandidate

MIN_SPLIT_CANDIDATES = 40
CHUNK_CANDIDATES = 30

_SECTION_PATH = ";section_path="
_REF_NUMBER = re.compile(r"^e([0-9]+)$")


def split_source(source: CollectedSource) -> list[CollectedSource]:
    """나눌 필요가 없거나 원문을 후보 순서대로 자를 수 없으면 원래 Source 하나를 돌려준다"""
    candidates = source.evidence_candidates
    if source.source_type != "notion" or len(candidates) < MIN_SPLIT_CANDIDATES:
        return [source]
    segments = _segments(source)
    if segments is None:
        return [source]

    # 제목·DB 속성처럼 섹션이 없는 후보는 모든 조각의 공통 맥락으로 넣는다
    shared = [i for i, c in enumerate(candidates) if _top_section(c) is None]
    sections: list[list[int]] = []
    for index, candidate in enumerate(candidates):
        name = _top_section(candidate)
        if name is None:
            continue
        if sections and _top_section(candidates[sections[-1][-1]]) == name:
            sections[-1].append(index)
        else:
            sections.append([index])

    groups: list[list[int]] = []
    for section in sections:
        if groups and len(groups[-1]) + len(section) <= CHUNK_CANDIDATES:
            groups[-1].extend(section)
        else:
            groups.append(list(section))
    if len(groups) < 2:
        return [source]

    return [
        source.model_copy(
            update={
                "content": "\n\n".join(segments[i] for i in indexes),
                "evidence_candidates": [candidates[i] for i in indexes],
            }
        )
        for indexes in (sorted(shared + group) for group in groups)
    ]


def merge_extractions(results: list[ExtractionResult]) -> ExtractionResult:
    """조각마다 따로 매긴 e번호를 앞 조각의 최대 번호만큼 밀어 겹치지 않게 합친다"""
    merged = ExtractionResult()
    offset = 0
    for result in results:
        merged.entities.extend(
            e.model_copy(update={"ref": _shift(e.ref, offset)}) for e in result.entities
        )
        merged.facts.extend(
            f.model_copy(update={"entity_ref": _shift(f.entity_ref, offset)}) for f in result.facts
        )
        merged.relations.extend(
            r.model_copy(
                update={
                    "subject_ref": _shift(r.subject_ref, offset),
                    "object_ref": _shift(r.object_ref, offset),
                }
            )
            for r in result.relations
        )
        merged.entity_evidence.extend(
            link.model_copy(update={"entity_ref": _shift(link.entity_ref, offset)})
            for link in result.entity_evidence
        )
        offset += _max_ref_number(result)
    return merged


def _top_section(candidate: EvidenceCandidate) -> str | None:
    path = candidate.locator.partition(_SECTION_PATH)[2]
    return path.split(" > ")[0] if path else None


def _segments(source: CollectedSource) -> list[str] | None:
    """content를 근거 후보 하나당 한 조각으로 자른다. Notion 본문 줄은 후보 순서와 같다"""
    content = source.content
    starts = [0]
    cursor = 0
    for candidate in source.evidence_candidates[1:]:
        position = content.find(candidate.snippet, cursor)
        if position < 0:
            return None
        starts.append(content.rfind("\n\n", 0, position) + 2)
        cursor = position + len(candidate.snippet)
    starts.append(len(content) + 2)
    segments = [content[start : end - 2] for start, end in zip(starts, starts[1:], strict=False)]
    return segments if "\n\n".join(segments) == content else None


def _shift(ref: str, offset: int) -> str:
    match = _REF_NUMBER.match(ref)
    return f"e{int(match.group(1)) + offset}" if match else ref


def _max_ref_number(result: ExtractionResult) -> int:
    refs = [
        *(e.ref for e in result.entities),
        *(f.entity_ref for f in result.facts),
        *(ref for r in result.relations for ref in (r.subject_ref, r.object_ref)),
        *(link.entity_ref for link in result.entity_evidence),
    ]
    numbers = [int(m.group(1)) for ref in refs if ref != SELF_REF and (m := _REF_NUMBER.match(ref))]
    return max(numbers, default=0)
