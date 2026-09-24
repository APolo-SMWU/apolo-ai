-- 최초 KG 테이블. ai 스키마와 AI 계정은 미리 준비해야 한다.
-- 기존 테이블이 있으면 오류로 중단한다. 반복 실행으로 스키마 변경을 숨기지 않는다.
-- 향후 변경은 이 파일 수정 대신 새 마이그레이션으로 관리한다.

CREATE TABLE ai.knowledge_graphs (
    id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE CHECK (user_id > 0),
    ontology_schema_version TEXT NOT NULL CHECK (btrim(ontology_schema_version) <> ''),
    version INTEGER NOT NULL CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE ai.entities (
    id UUID PRIMARY KEY,
    graph_id UUID NOT NULL REFERENCES ai.knowledge_graphs(id) ON DELETE CASCADE,
    class_type TEXT NOT NULL CHECK (
        class_type IN ('Person', 'Education', 'Experience', 'Organization', 'Channel')
    ),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'review', 'retracted')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (graph_id, id)
);

-- DB는 최대 1개를 보장하고, 정확히 1개인지는 KG 검증 함수가 확인한다.
CREATE UNIQUE INDEX one_active_person_per_graph
    ON ai.entities (graph_id) WHERE class_type = 'Person' AND status = 'active';

CREATE TABLE ai.facts (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES ai.entities(id) ON DELETE CASCADE,
    predicate TEXT NOT NULL CHECK (btrim(predicate) <> ''),
    value JSONB NOT NULL,
    value_type TEXT NOT NULL CHECK (value_type IN ('string', 'uri')),
    origin TEXT NOT NULL CHECK (origin IN ('user', 'extracted')),
    confidence DOUBLE PRECISION CHECK (confidence >= 0 AND confidence <= 1),
    locked BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'candidate', 'retracted')),
    updated_at TIMESTAMPTZ NOT NULL,
    -- 현재 Seed는 문자열과 URI만 사용한다. 외부 추출 단계에서 지원 타입을 확장한다.
    CHECK (jsonb_typeof(value) = 'string')
);

CREATE INDEX facts_entity_id_idx ON ai.facts (entity_id);

CREATE TABLE ai.relations (
    id UUID PRIMARY KEY,
    graph_id UUID NOT NULL REFERENCES ai.knowledge_graphs(id) ON DELETE CASCADE,
    subject_entity_id UUID NOT NULL,
    predicate TEXT NOT NULL CHECK (
        predicate IN ('hasEducation', 'hasExperience', 'hasChannel', 'atOrganization')
    ),
    object_entity_id UUID NOT NULL,
    origin TEXT NOT NULL CHECK (origin IN ('user', 'extracted')),
    confidence DOUBLE PRECISION CHECK (confidence >= 0 AND confidence <= 1),
    locked BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'candidate', 'retracted')),
    updated_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (graph_id, subject_entity_id)
        REFERENCES ai.entities(graph_id, id) ON DELETE CASCADE,
    FOREIGN KEY (graph_id, object_entity_id)
        REFERENCES ai.entities(graph_id, id) ON DELETE CASCADE
);

CREATE INDEX relations_subject_idx ON ai.relations (graph_id, subject_entity_id);
CREATE INDEX relations_object_idx ON ai.relations (graph_id, object_entity_id);
