from fastapi import APIRouter, Depends
from app.ai.query_engine import QueryEngine
from app.core.auth import require_permission
from app.core.permissions import Permission, UserContext

router = APIRouter(prefix="/query", tags=["AI Query"])
engine = QueryEngine()

@router.post("/")
def query(question: str, user: UserContext = Depends(require_permission(Permission.AI_QUERY_BUSINESS))):
    return engine.ask(question)
