-- 005 적용 후 실행한다. 실행 모듈이 전체 DDL을 한 트랜잭션으로 처리한다.
-- Personal Ontology 2.0: Activity 추가, broader 제거, 폐기 속성 정리.
-- 폐기된 Fact·Relation은 이력 보존을 위해 삭제하지 않고 retracted로 남긴다.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM ai.knowledge_graphs
        WHERE ontology_schema_version <> '1.1'
    ) THEN
        RAISE EXCEPTION
            '온톨로지 1.1이 아닌 KG가 있어 2.0 마이그레이션을 적용할 수 없습니다.';
    END IF;
END $$;

ALTER TABLE ai.entities DROP CONSTRAINT entities_class_type_check;
ALTER TABLE ai.entities ADD CONSTRAINT entities_class_type_check CHECK (
    class_type IN (
        'Person', 'Education', 'Experience', 'Activity', 'Work', 'Credential',
        'Skill', 'Organization', 'Channel'
    )
);

-- v1.1 Experience.unit은 v2의 department로 이름을 바꾼다.
UPDATE ai.facts fact
SET predicate = 'department', updated_at = CURRENT_TIMESTAMP
FROM ai.entities entity
WHERE fact.entity_id = entity.id
  AND entity.class_type = 'Experience'
  AND fact.predicate = 'unit';

-- v2에서 제거한 속성은 원문 이력을 남기되 현재 KG에서는 사용하지 않는다.
UPDATE ai.facts fact
SET status = 'retracted', updated_at = CURRENT_TIMESTAMP
FROM ai.entities entity
WHERE fact.entity_id = entity.id
  AND fact.status <> 'retracted'
  AND (
      (entity.class_type = 'Person' AND fact.predicate = 'photoRef')
      OR (entity.class_type = 'Education' AND fact.predicate = 'expectedEnd')
      OR (entity.class_type = 'Experience' AND fact.predicate = 'sourceDescription')
      OR (entity.class_type = 'Work' AND fact.predicate = 'sourceDescription')
      OR (entity.class_type = 'Skill' AND fact.predicate = 'proficiency')
      OR (entity.class_type = 'Organization' AND fact.predicate = 'address')
      OR (entity.class_type = 'Channel' AND fact.predicate = 'label')
  );

-- v2 MVP에서는 Skill 계층 관계를 사용하지 않는다.
UPDATE ai.relations
SET status = 'retracted', updated_at = CURRENT_TIMESTAMP
WHERE predicate = 'broader' AND status <> 'retracted';

ALTER TABLE ai.relations DROP CONSTRAINT relations_predicate_check;
ALTER TABLE ai.relations ADD CONSTRAINT relations_predicate_check CHECK (
    predicate IN (
        'hasEducation', 'hasExperience', 'participatedIn', 'holds', 'hasSkill', 'hasChannel',
        'atOrganization', 'usesSkill', 'partOf'
    )
    OR (predicate = 'broader' AND status = 'retracted')
);

UPDATE ai.knowledge_graphs
SET ontology_schema_version = '2.0', updated_at = CURRENT_TIMESTAMP
WHERE ontology_schema_version = '1.1';
