from fastapi import FastAPI
from app.api.products import router as product_router

app = FastAPI(title="Retail Sales Intelligence Platform")

app.include_router(product_router)


@app.get("/")
def root():
    return {"message": "Retail Sales Intelligence Platform API is running"}