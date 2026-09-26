-- 001 적용 후 실행한다. 실행 모듈이 전체 DDL을 한 트랜잭션으로 처리한다.
-- 기존 PK가 있으므로 아래 UNIQUE 제약은 기존 데이터의 허용 범위를 바꾸지 않는다.
ALTER TABLE ai.facts ADD CONSTRAINT facts_id_entity_unique UNIQUE (id, entity_id);
ALTER TABLE ai.relations ADD CONSTRAINT relations_graph_id_unique UNIQUE (graph_id, id);

CREATE TABLE ai.source_documents (
    id UUID PRIMARY KEY,
    graph_id UUID NOT NULL REFERENCES ai.knowledge_graphs(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (source_type IN ('github', 'notion')),
    source_key TEXT NOT NULL CHECK (source_key ~ '[^[:space:]]'),
    source_url TEXT NOT NULL CHECK (source_url ~ '[^[:space:]]'),
    processed_at TIMESTAMPTZ,
    UNIQUE (graph_id, source_key),
    UNIQUE (graph_id, id)
);

CREATE TABLE ai.source_snapshots (
    id UUID PRIMARY KEY,
    graph_id UUID NOT NULL,
    source_key TEXT NOT NULL,
    content_hash TEXT CHECK (content_hash ~ '[^[:space:]]'),
    source_version TEXT CHECK (source_version ~ '[^[:space:]]'),
    last_fetched_at TIMESTAMPTZ NOT NULL,
    fetch_status TEXT NOT NULL CHECK (fetch_status IN ('success', 'inaccessible', 'error')),
    CHECK (fetch_status <> 'success' OR content_hash IS NOT NULL),
    UNIQUE (graph_id, source_key),
    FOREIGN KEY (graph_id, source_key)
        REFERENCES ai.source_documents(graph_id, source_key) ON DELETE CASCADE
);

CREATE TABLE ai.evidence (
    id UUID PRIMARY KEY,
    -- 연결 대상과 같은 KG인지 DB에서 검증하기 위한 저장 전용 필드.
    graph_id UUID NOT NULL,
    source_document_id UUID NOT NULL,
    snippet TEXT NOT NULL CHECK (snippet ~ '[^[:space:]]'),
    locator TEXT NOT NULL CHECK (locator ~ '[^[:space:]]'),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (graph_id, id),
    FOREIGN KEY (graph_id, source_document_id)
        REFERENCES ai.source_documents(graph_id, id) ON DELETE CASCADE
);
CREATE INDEX evidence_source_idx ON ai.evidence (graph_id, source_document_id);

CREATE TABLE ai.fact_evidence (
    graph_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    fact_id UUID NOT NULL,
    evidence_id UUID NOT NULL,
    PRIMARY KEY (fact_id, evidence_id),
    -- KG 전체 삭제의 cascade가 끝난 후 검사한다. 단독 삭제는 commit 시 차단된다.
    FOREIGN KEY (graph_id, entity_id) REFERENCES ai.entities(graph_id, id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (fact_id, entity_id) REFERENCES ai.facts(id, entity_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (graph_id, evidence_id)
        REFERENCES ai.evidence(graph_id, id) ON DELETE CASCADE
);
CREATE INDEX fact_evidence_evidence_idx ON ai.fact_evidence (graph_id, evidence_id);
CREATE INDEX fact_evidence_entity_idx ON ai.fact_evidence (graph_id, entity_id);

CREATE TABLE ai.relation_evidence (
    graph_id UUID NOT NULL,
    relation_id UUID NOT NULL,
    evidence_id UUID NOT NULL,
    PRIMARY KEY (relation_id, evidence_id),
    FOREIGN KEY (graph_id, relation_id) REFERENCES ai.relations(graph_id, id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (graph_id, evidence_id)
        REFERENCES ai.evidence(graph_id, id) ON DELETE CASCADE
);
CREATE INDEX relation_evidence_evidence_idx ON ai.relation_evidence (graph_id, evidence_id);
