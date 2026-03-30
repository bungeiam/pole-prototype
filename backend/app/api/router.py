from fastapi import APIRouter
from app.api.routes.documents import router as documents_router
from app.api.routes.poles import router as poles_router
from app.api.routes.summary import router as summary_router


api_router = APIRouter()
api_router.include_router(documents_router)
api_router.include_router(poles_router)
api_router.include_router(summary_router)