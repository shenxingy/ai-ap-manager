from fastapi import APIRouter

from app.api.v1 import admin, auth, invoices, match, exceptions, approvals, kpi, users, vendors
from app.api.v1 import fraud_incidents, recurring_patterns
from app.api.v1 import approval_matrix as am_module

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(am_module.delegation_router, prefix="/users", tags=["approval-matrix"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
api_router.include_router(match.router, prefix="/invoices", tags=["match"])
api_router.include_router(exceptions.router, prefix="/exceptions", tags=["exceptions"])
api_router.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
api_router.include_router(kpi.router, prefix="/kpi", tags=["kpi"])
api_router.include_router(vendors.router, prefix="/vendors", tags=["vendors"])
api_router.include_router(fraud_incidents.router, prefix="/fraud-incidents", tags=["fraud"])
api_router.include_router(recurring_patterns.router, prefix="/admin", tags=["admin"])
api_router.include_router(am_module.router, prefix="/approval-matrix", tags=["approval-matrix"])
