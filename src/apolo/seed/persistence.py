"""프로필의 최초 저장·동일 내용 재사용·변경 반영을 연결한다."""

from datetime import datetime
from uuid import uuid4

import psycopg

from apolo.contracts.kg import SeedKnowledgeGraph
from apolo.contracts.profile import SeedProfileInput
from apolo.db.seed import load_seed_by_user_id, save_initial_seed, update_profile_seed
from apolo.seed.profile import build_initial_profile_seed
from apolo.seed.update import build_updated_profile_seed


def ensure_profile_seed(
    connection: psycopg.Connection, source: SeedProfileInput, *, now: datetime
) -> SeedKnowledgeGraph:
    """없으면 저장하고, 같은 내용이면 저장된 ID·시간·버전을 그대로 반환한다.

    현재 프로필만으로 구성된 Seed KG 전용이다. 최신 전체 프로필로 변경을 반영한다.
    PostgreSQL 기본 READ COMMITTED를 전제로 동시 최초 저장의 사용자 중복만 처리한다.
    기존 트랜잭션 안에서는 최종 commit을 호출부가 담당한다.
    """
    candidate = build_initial_profile_seed(source, graph_id=uuid4(), now=now)
    with connection.transaction():
        existing = load_seed_by_user_id(connection, source.user_id)
        if existing is None:
            try:
                save_initial_seed(connection, candidate)
            except psycopg.errors.UniqueViolation as error:
                # 다른 요청이 먼저 생성했을 수 있다. 다른 종류의 충돌은 숨기지 않는다.
                if error.diag.constraint_name != "knowledge_graphs_user_id_key":
                    raise
                existing = load_seed_by_user_id(connection, source.user_id)
                if existing is None:
                    raise
            else:
                return candidate

        updated = build_updated_profile_seed(existing, source, now=now)
        if updated.version != existing.version:
            update_profile_seed(connection, existing, updated)
        return updated
