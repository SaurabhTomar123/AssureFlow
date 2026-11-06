from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import settings
from src.api.routes_shops import router as shops_router
from src.api.routes_bills import router as bills_router
from src.api.routes_issues import router as issues_router
from src.api.routes_summary import router as summary_router
from src.api.routes_advisory import router as advisory_router
from src.api.routes_users import router as users_router
from src.api.routes_inventory import router as inventory_router
from src.api.routes_staff import router as staff_router
from src.api.routes_notifications import router as notifications_router
from src.dashboard.router import router as dashboard_router
from src.api.routes_auth import router as auth_router
from src.api.routes_gsp import router as gsp_router
from src.api.routes_bank import router as bank_router
from src.switch_bridge.whatsapp_webhook import router as whatsapp_router
from src.api.routes_concierge import router as concierge_router
from src.api.routes_voice import router as voice_router
from fastapi import Request
from fastapi.responses import JSONResponse

app = FastAPI(
    title="MunimJi Core API",
    description="Automated GST Accounting, Store Operations & Manager Suite for Indian MSMEs & CAs",
    version="2.0.0",
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred.", "error_type": type(exc).__name__},
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
app.include_router(advisory_router)
app.include_router(users_router)
app.include_router(inventory_router)
app.include_router(staff_router)
app.include_router(notifications_router)
app.include_router(dashboard_router)
app.include_router(auth_router)
app.include_router(gsp_router)
app.include_router(bank_router)
app.include_router(whatsapp_router)
app.include_router(concierge_router)
app.include_router(voice_router)


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

