"""Graph B 출력을 현재 KG의 정규값에 맞춰 안전하게 정리한다"""

from apolo.contracts.content import GraphBOutput
from apolo.contracts.generate import (
    AboutBlock,
    ActivitiesBlock,
    AwardsBlock,
    CertificationBlock,
    EducationBlock,
    ExperienceBlock,
    WorksBlock,
)
from apolo.contracts.knowledge import ActiveKnowledgeGraph
from apolo.graph_b.normalizers.credentials import (
    deduplicate_credential_items,
    normalize_award_items,
    normalize_certification_items,
)
from apolo.graph_b.normalizers.timeline import (
    deduplicate_timeline_items,
    normalize_activity_items,
    normalize_education_items,
    normalize_experience_items,
)
from apolo.graph_b.normalizers.works import (
    deduplicate_work_items,
    merge_project_participation_into_works,
    normalize_work_items,
)


def normalize_graph_b_output(output: GraphBOutput, graph: ActiveKnowledgeGraph) -> GraphBOutput:
    """LLM 표현을 KG 근거에 맞춰 보정하고 근거 없는 item을 제거한다"""

    normalized_blocks = []
    about_seen = False
    for block in output.blocks:
        if isinstance(block, AboutBlock):
            if not about_seen:
                normalized_blocks.append(block)
                about_seen = True
            continue
        if isinstance(block, EducationBlock):
            items = normalize_education_items(block.items, graph)
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, ExperienceBlock):
            items = deduplicate_timeline_items(
                normalize_experience_items(block.items, graph), graph
            )
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, ActivitiesBlock):
            items = deduplicate_timeline_items(normalize_activity_items(block.items, graph), graph)
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, AwardsBlock):
            items = deduplicate_credential_items(normalize_award_items(block.items, graph))
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, CertificationBlock):
            items = deduplicate_credential_items(normalize_certification_items(block.items, graph))
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))
        elif isinstance(block, WorksBlock):
            items = deduplicate_work_items(normalize_work_items(block.items, graph), graph)
            if items:
                normalized_blocks.append(block.model_copy(update={"items": items}))

    if not about_seen:
        normalized_blocks.insert(0, AboutBlock(description=""))
    normalized_blocks = merge_project_participation_into_works(normalized_blocks, graph)
    return GraphBOutput(blocks=normalized_blocks)
