from fastapi import APIRouter

from app.api.v1 import auth, invoices, match, exceptions

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
api_router.include_router(match.router, prefix="/invoices", tags=["match"])
api_router.include_router(exceptions.router, prefix="/exceptions", tags=["exceptions"])
