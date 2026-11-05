from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings
from src.api.routes_shops import router as shops_router
from src.api.routes_bills import router as bills_router
from src.api.routes_issues import router as issues_router
from src.api.routes_summary import router as summary_router

app = FastAPI(
    title="MunimJi Core API",
    description="Automated GST Accounting and Compliance Pipeline for Indian MSMEs & CAs",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(shops_router)
app.include_router(bills_router)
app.include_router(issues_router)
app.include_router(summary_router)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "MunimJi",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/")
def root():
    return {
        "message": "MunimJi GST Intelligence Engine",
        "docs_url": "/docs",
        "core_rule": "AI reads, code checks, human decides",
    }
