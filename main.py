from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os

from app.api.products import router as products_router
from app.api.inventory import router as inventory_router
from app.api.bills import router as bills_router
from app.api.analytics import router as analytics_router
from app.api.purchase import router as purchase_router
from app.api.supliers import router as suppliers_router
from app.api.query import router as query_router


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
)


app.include_router(products_router)
app.include_router(inventory_router)
app.include_router(bills_router)
app.include_router(analytics_router)
app.include_router(purchase_router)
app.include_router(suppliers_router)
app.include_router(query_router)


@app.get("/")
def root(request: Request = None):
    if request and "text/html" in request.headers.get("accept", "") and os.path.exists("index.html"):
        return FileResponse("index.html")
    return {
        "message": "Retail Sales Intelligence Platform API is running"
    }


@app.get("/app")
def serve_app():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {
        "message": "Retail Sales Intelligence Platform API is running"
    }