"""Graph A LangGraph 실행 상태"""

from datetime import datetime
from typing import NotRequired, TypedDict
from uuid import UUID

import psycopg

from apolo.extraction.entity_linking import Linker
from apolo.graph_a.processing import CandidateExtractor, GraphAProcessingResult
from apolo.source_collection import StoredPublicCollection


class GraphAState(TypedDict):
    """수집 결과와 처리 결과를 전달하는 Graph A 상태"""

    connection: psycopg.Connection
    graph_id: UUID
    collection: StoredPublicCollection
    extractor: CandidateExtractor
    linker: NotRequired[Linker | None]
    now: datetime | None
    result: GraphAProcessingResult | None
