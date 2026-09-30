-- Work·Activity 설명 생성용 원문 근거를 Fact/Relation과 별도로 Entity에 연결한다.
CREATE TABLE ai.entity_evidence (
    graph_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    evidence_id UUID NOT NULL,
    PRIMARY KEY (entity_id, evidence_id),
    FOREIGN KEY (graph_id, entity_id)
        REFERENCES ai.entities(graph_id, id) ON DELETE CASCADE,
    FOREIGN KEY (graph_id, evidence_id)
        REFERENCES ai.evidence(graph_id, id) ON DELETE CASCADE
);

CREATE INDEX entity_evidence_evidence_idx
    ON ai.entity_evidence (graph_id, evidence_id);
