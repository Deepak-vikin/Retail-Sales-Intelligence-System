from fastapi import APIRouter
from app.ai.query_engine import QueryEngine

router = APIRouter(prefix="/query", tags=["AI Query"])
engine = QueryEngine()
@router.post("/")
def query(question: str):
    return engine.ask(question)