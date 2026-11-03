-- 사용자가 올린 파일(PDF 등)을 Source로 저장한다. 기존 데이터는 바뀌지 않는다.
ALTER TABLE ai.source_documents DROP CONSTRAINT source_documents_source_type_check;
ALTER TABLE ai.source_documents ADD CONSTRAINT source_documents_source_type_check
    CHECK (source_type IN ('github', 'notion', 'file'));
