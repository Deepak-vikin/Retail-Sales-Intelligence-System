from fastapi import FastAPI
from app.api.products import router as product_router
from app.api.inventory import router as inventory_router
from app.api.bills import router as bill_router
from app.api.analytics import router as analytics_router
app = FastAPI(title="Retail Sales Intelligence Platform")
app.include_router(analytics_router)
app.include_router(product_router)
app.include_router(inventory_router)
app.include_router(bill_router)

@app.get("/")
def root():
    return {"message": "Retail Sales Intelligence Platform API is running"}