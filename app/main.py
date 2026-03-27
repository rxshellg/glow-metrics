from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import products, ingredients, admin

app = FastAPI(
    title="Glow Metrics API",
    description="Analytics platform for skincare products and ingredients",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(ingredients.router)
app.include_router(admin.router)

@app.get("/")
def read_root():
    return {
        "message": "Welcome to Glow Metrics API",
        "docs": "/docs",
        "status": "running"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}