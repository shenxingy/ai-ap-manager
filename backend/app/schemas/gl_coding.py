"""GL Smart Coding Pydantic schemas."""
import uuid

from pydantic import BaseModel


class GLLineSuggestion(BaseModel):
    line_id: uuid.UUID
    line_number: int
    description: str | None
    gl_account: str | None          # suggested GL account code
    cost_center: str | None         # suggested cost center
    confidence_pct: float           # 0.0-1.0 (frequency-based)
    source: str                     # "vendor_history" | "po_line" | "category_default" | "none"


class GLSuggestionResponse(BaseModel):
    invoice_id: uuid.UUID
    suggestions: list[GLLineSuggestion]
