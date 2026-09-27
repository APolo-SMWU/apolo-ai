-- 003 적용 후 실행한다. 실행 모듈이 전체 DDL을 한 트랜잭션으로 처리한다.
-- Fact·Relation이 어느 입력에서 왔는지 기록한다. Entity는 프로필과 외부 소스가
-- 함께 참조할 수 있으므로 출처를 표시하지 않는다.
-- 지금까지는 프로필 Seed만 저장했으므로 기존 행은 profile로 채운다.
-- 추출 데이터가 이미 있으면 출처를 추정하지 않고 중단한다.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM ai.facts WHERE origin <> 'user')
        OR EXISTS (SELECT 1 FROM ai.relations WHERE origin <> 'user') THEN
        RAISE EXCEPTION
            '프로필 외 Fact·Relation이 존재하여 출처를 자동으로 채울 수 없습니다. 수동 이관이 필요합니다.';
    END IF;
END $$;

-- 기본값은 기존 행을 채우는 데만 쓰고 제거한다.
-- 새 저장 코드가 출처를 빠뜨리면 INSERT가 실패하도록 한다.
ALTER TABLE ai.facts
    ADD COLUMN provenance TEXT NOT NULL DEFAULT 'profile'
        CHECK (provenance IN ('profile', 'requirements', 'source'));
ALTER TABLE ai.facts ALTER COLUMN provenance DROP DEFAULT;

ALTER TABLE ai.relations
    ADD COLUMN provenance TEXT NOT NULL DEFAULT 'profile'
        CHECK (provenance IN ('profile', 'requirements', 'source'));
ALTER TABLE ai.relations ALTER COLUMN provenance DROP DEFAULT;
