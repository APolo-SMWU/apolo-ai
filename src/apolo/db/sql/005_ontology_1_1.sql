-- 004 적용 후 실행한다. 실행 모듈이 전체 DDL을 한 트랜잭션으로 처리한다.
-- Personal Ontology 1.1: 추출용 Class·Relation·값 타입, Entity 식별자, 분석 해시를 추가한다.
-- 기존 제약을 넓히기만 하므로 기존 데이터는 그대로 통과한다.

ALTER TABLE ai.entities DROP CONSTRAINT entities_class_type_check;
ALTER TABLE ai.entities ADD CONSTRAINT entities_class_type_check CHECK (
    class_type IN (
        'Person', 'Education', 'Experience', 'Work', 'Credential', 'Skill', 'Organization', 'Channel'
    )
);

ALTER TABLE ai.relations DROP CONSTRAINT relations_predicate_check;
ALTER TABLE ai.relations ADD CONSTRAINT relations_predicate_check CHECK (
    predicate IN (
        'hasEducation', 'hasExperience', 'participatedIn', 'holds', 'hasChannel',
        'atOrganization', 'usesSkill', 'partOf', 'broader'
    )
);

ALTER TABLE ai.facts DROP CONSTRAINT facts_value_type_check;
ALTER TABLE ai.facts ADD CONSTRAINT facts_value_type_check
    CHECK (value_type IN ('string', 'uri', 'date', 'boolean'));

-- boolean은 JSON true/false, 나머지는 JSON 문자열로 저장한다.
ALTER TABLE ai.facts DROP CONSTRAINT facts_value_check;
ALTER TABLE ai.facts ADD CONSTRAINT facts_value_check CHECK (
    jsonb_typeof(value) = CASE WHEN value_type = 'boolean' THEN 'boolean' ELSE 'string' END
);

-- Entity Resolution용 식별자. 강한 식별자는 같은 KG에서 한 Entity만 가진다.
CREATE TABLE ai.entity_keys (
    graph_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    key_type TEXT NOT NULL CHECK (key_type ~ '[^[:space:]]'),
    key_value TEXT NOT NULL CHECK (key_value ~ '[^[:space:]]'),
    is_strong BOOLEAN NOT NULL,
    PRIMARY KEY (entity_id, key_type, key_value),
    FOREIGN KEY (graph_id, entity_id) REFERENCES ai.entities(graph_id, id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX entity_keys_strong_unique
    ON ai.entity_keys (graph_id, key_type, key_value) WHERE is_strong;

-- 마지막으로 분석을 마친 원문 해시. 분석 시각과 함께 기록한다.
ALTER TABLE ai.source_documents
    ADD COLUMN processed_content_hash TEXT CHECK (processed_content_hash ~ '[^[:space:]]');
ALTER TABLE ai.source_documents ADD CONSTRAINT source_documents_processed_pair_check
    CHECK ((processed_at IS NULL) = (processed_content_hash IS NULL));

-- 1.1은 1.0에 추가만 했으므로 기존 KG를 1.1로 올린다. KG 데이터 버전(version)은 바꾸지 않는다.
UPDATE ai.knowledge_graphs SET ontology_schema_version = '1.1'
WHERE ontology_schema_version = '1.0';
