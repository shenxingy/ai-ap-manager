"""Pydantic schemas for CSV bulk import results."""
from pydantic import BaseModel


class ImportRowError(BaseModel):
    row: int
    field: str
    message: str


class ImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[ImportRowError]
    warnings: list[str] = []
