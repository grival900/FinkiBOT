import logging
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@event.listens_for(engine, "connect")
def _configure_pgvector(dbapi_connection, _connection_record) -> None:
    """Widen pgvector's HNSW search on every connection.

    By default the HNSW index scan collects only `hnsw.ef_search` (40) candidates and
    *then* applies the query's WHERE clause. `core/retrieval.search()` filters by
    `source` on each call, so for a query whose ~40 globally-nearest chunks all belong
    to one source, the scan for the *other* source has nothing left after filtering and
    returns zero rows — silently defeating the per-source union that function is built
    on (worst hit: a person/course lookup where finki_hub's short cards crowd the
    nearest-neighbour list and the official prose never shows up). `iterative_scan`
    lets the index keep walking past the first window until `LIMIT` is met
    post-filter; `relaxed_order` is fine because every caller re-sorts by score. The
    `::vector` probe forces the extension's library to load so its GUCs are registered
    before we SET them on a fresh backend."""
    try:
        cur = dbapi_connection.cursor()
        try:
            cur.execute("SELECT '[1]'::vector")
            cur.execute("SET hnsw.iterative_scan = relaxed_order")
            cur.execute("SET hnsw.ef_search = 100")
        finally:
            cur.close()
        dbapi_connection.commit()
    except Exception:
        logger.warning("Could not configure pgvector HNSW search parameters", exc_info=True)
        try:
            dbapi_connection.rollback()
        except Exception:
            pass


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
