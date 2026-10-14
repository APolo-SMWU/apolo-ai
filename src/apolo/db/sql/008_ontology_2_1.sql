-- 007 적용 후 실행한다. 실행 모듈이 전체 DDL을 한 트랜잭션으로 처리한다.
-- Personal Ontology 2.1: Skill.kind 추가, Skill.category를 표시 그룹 id로 제한.
-- 분석 시점의 온톨로지 버전을 기록해 규칙이 바뀐 Source를 다시 추출한다.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM ai.knowledge_graphs
        WHERE ontology_schema_version <> '2.0'
    ) THEN
        RAISE EXCEPTION
            '온톨로지 2.0이 아닌 KG가 있어 2.1 마이그레이션을 적용할 수 없습니다.';
    END IF;
END $$;

-- 기존 분석 문서는 버전이 없으므로 다음 생성 때 다시 추출된다. 근거 해시는 유지한다.
ALTER TABLE ai.source_documents
    ADD COLUMN processed_ontology_version TEXT
        CHECK (processed_ontology_version ~ '[^[:space:]]');
ALTER TABLE ai.source_documents ADD CONSTRAINT source_documents_processed_version_check
    CHECK (processed_at IS NOT NULL OR processed_ontology_version IS NULL);

-- 이전 표시 그룹 이름으로 저장된 category는 이력으로 남기고 사용하지 않는다.
UPDATE ai.facts fact
SET status = 'retracted', updated_at = CURRENT_TIMESTAMP
FROM ai.entities entity
WHERE fact.entity_id = entity.id
  AND entity.class_type = 'Skill'
  AND fact.predicate = 'category'
  AND fact.status <> 'retracted'
  AND fact.value #>> '{}' NOT IN (
        'language',
        'web_markup_styling',
        'frontend',
        'ui_component',
        'backend',
        'mobile',
        'desktop',
        'state_management',
        'server_state_data_fetching',
        'api_communication',
        'database',
        'orm_data_access',
        'cache_search',
        'messaging_event_streaming',
        'auth_security',
        'architecture_design',
        'build_package_tool',
        'dev_automation_tool',
        'ci_cd',
        'container_infra_automation',
        'cloud_deployment',
        'storage_cdn',
        'os_server',
        'network',
        'testing_quality',
        'monitoring_observability',
        'data_collection_processing',
        'data_pipeline',
        'data_warehouse_lakehouse',
        'data_analysis_bi',
        'data_visualization',
        'statistics_experiment',
        'machine_learning',
        'nlp_computer_vision',
        'generative_ai_llm',
        'vector_search',
        'knowledge_graph_ontology',
        'mlops_model_serving',
        'design_prototyping',
        'docs_collaboration',
        'game_realtime_graphics',
        'embedded_iot',
        'other'
  );

UPDATE ai.knowledge_graphs
SET ontology_schema_version = '2.1', updated_at = CURRENT_TIMESTAMP
WHERE ontology_schema_version = '2.0';
