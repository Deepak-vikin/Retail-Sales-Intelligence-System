import os
import time
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.products import router as products_router
from app.api.inventory import router as inventory_router
from app.api.bills import router as bills_router
from app.api.analytics import router as analytics_router
from app.api.purchase import router as purchase_router
from app.api.supliers import router as suppliers_router
from app.api.query import router as query_router
from app.api.employees import router as employees_router
from app.api.system import router as system_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Retail Sales Intelligence Platform",
    description="AI-powered retail sales and inventory intelligence system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Server-Timing", "Content-Disposition"],
)

@app.middleware("http")
async def performance_profiling_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start_time) * 1000
    response.headers["Server-Timing"] = f"total;dur={duration_ms:.2f}"
    # Structured audit logging of request duration without exposing secrets or tokens
    logger.info(
        "[PERF_HTTP] %s %s -> status=%d duration=%.2fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

app.include_router(products_router)
app.include_router(inventory_router)
app.include_router(bills_router)
app.include_router(analytics_router)
app.include_router(purchase_router)
app.include_router(suppliers_router)
app.include_router(query_router)
app.include_router(employees_router)
app.include_router(system_router)

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_INDEX = BACKEND_DIR.parent / "frontend" / "index.html"

def get_frontend_file():
    if FRONTEND_INDEX.is_file():
        return str(FRONTEND_INDEX)
    if os.path.exists("index.html"):
        return "index.html"
    return None

@app.get("/")
def root(request: Request = None):
    frontend_path = get_frontend_file()
    if request and "text/html" in request.headers.get("accept", "") and frontend_path:
        return FileResponse(frontend_path)
    return {
        "message": "Retail Sales Intelligence Platform API is running"
    }

@app.get("/app")
def serve_app():
    frontend_path = get_frontend_file()
    if frontend_path:
        return FileResponse(frontend_path)
    return {
        "message": "Retail Sales Intelligence Platform API is running"
    }
