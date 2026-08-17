from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.schemas import SearchResultOut
from backend.core.retrieval import search
from backend.db import get_db

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=list[SearchResultOut])
def search_documents(
    q: str,
    source: str | None = None,
    type: str | None = None,
    limit: int = 10,
    db: Session = Depends(get_db),
) -> list[SearchResultOut]:
    results = search(db, q, k=limit, source=source, type=type)
    return [SearchResultOut(**r.__dict__) for r in results]
