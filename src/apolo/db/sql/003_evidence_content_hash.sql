-- 002 적용 후 Evidence가 없는 개발 DB에서 한 번 실행한다.
-- 기존 Evidence는 어느 원문 해시에서 왔는지 복원할 수 없으므로 자동 추정하지 않는다.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM ai.evidence) THEN
        RAISE EXCEPTION
            'Evidence가 존재하여 source_content_hash를 자동 추가할 수 없습니다. 수동 이관이 필요합니다.';
    END IF;
END $$;

ALTER TABLE ai.evidence
    ADD COLUMN source_content_hash TEXT NOT NULL CHECK (source_content_hash ~ '[^[:space:]]');

CREATE INDEX evidence_source_hash_idx
    ON ai.evidence (graph_id, source_document_id, source_content_hash);
