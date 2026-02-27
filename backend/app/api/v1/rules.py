"""Policy upload and rule lifecycle management API.

Endpoints:
  POST /rules/upload-policy   (ADMIN) — upload PDF/DOC/TXT, store in MinIO, enqueue AI extraction
  GET  /rules                 — list all rule versions
  GET  /rules/{id}            — rule version detail with config JSON
  PATCH /rules/{id}           — update config fields (human review)
  POST /rules/{id}/publish    — publish; supersede previous published version
  POST /rules/{id}/reject     — reject draft/in_review version
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, require_role
from app.db.session import get_session
from app.models.rule import Rule, RuleVersion
from app.services import storage as storage_svc

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Constants ───

ALLOWED_POLICY_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}
MAX_POLICY_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


# ─── Schemas ───

class RuleVersionListItem(BaseModel):
    id: uuid.UUID
    rule_id: uuid.UUID
    version_number: int
    status: str
    source: str | None
    ai_extracted: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RuleVersionDetail(RuleVersionListItem):
    config_json: str
    change_summary: str | None
    is_shadow_mode: bool


class RuleVersionListResponse(BaseModel):
    items: list[RuleVersionListItem]
    total: int


class PolicyUploadResponse(BaseModel):
    rule_id: uuid.UUID
    version_id: uuid.UUID
    file_key: str
    status: str
    message: str


class RuleVersionUpdate(BaseModel):
    config_json: str | None = None
    change_summary: str | None = None
    is_shadow_mode: bool | None = None


# ─── POST /upload-policy ───

@router.post(
    "/upload-policy",
    response_model=PolicyUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload AP policy document and trigger AI rule extraction (ADMIN only)",
)
async def upload_policy(
    file: Annotated[UploadFile, File(description="AP policy PDF, DOCX, or TXT, max 50 MB")],
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user=Depends(require_role("ADMIN")),
):
    """Upload a policy document, store in MinIO, create a draft RuleVersion, enqueue extraction."""
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_POLICY_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{content_type}'. Allowed: PDF, DOC, DOCX, TXT.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if len(content) > MAX_POLICY_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 50 MB limit.",
        )

    original_filename = file.filename or "policy.pdf"
    version_id = uuid.uuid4()
    file_key = f"policies/{version_id}/{original_filename}"

    # Upload to MinIO
    try:
        storage_svc.upload_file(
            bucket=settings.MINIO_BUCKET_NAME,
            object_name=file_key,
            data=content,
            content_type=content_type,
        )
    except Exception as exc:
        logger.error("MinIO upload failed for policy: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to store policy file. Please try again.",
        )

    # Create Rule (parent) + RuleVersion (draft)
    rule_name = f"policy_{original_filename[:60]}_{version_id.hex[:8]}"
    rule = Rule(
        name=rule_name,
        description=f"Extracted from policy upload: {original_filename}",
        rule_type="matching_tolerance",
        is_active=True,
    )
    db.add(rule)
    await db.flush()  # populate rule.id

    version = RuleVersion(
        id=version_id,
        rule_id=rule.id,
        version_number=1,
        status="draft",
        source="policy_upload",
        config_json="{}",
        ai_extracted=False,
        is_shadow_mode=False,
        change_summary=f"Initial upload from {original_filename}",
        created_by=current_user.id,
    )
    db.add(version)
    await db.commit()

    # Enqueue Celery task (import lazily to avoid circular imports at module load)
    try:
        from app.workers.rules_tasks import extract_rules_from_policy
        extract_rules_from_policy.delay(str(version_id), file_key)
        logger.info("Enqueued extract_rules_from_policy for version %s", version_id)
    except Exception as exc:
        logger.error("Failed to enqueue extraction task: %s", exc)
        # Non-fatal — version stays in draft; admin can re-trigger

    return PolicyUploadResponse(
        rule_id=rule.id,
        version_id=version_id,
        file_key=file_key,
        status="draft",
        message="Policy uploaded. AI rule extraction queued.",
    )


# ─── GET /rules ───

@router.get(
    "",
    response_model=RuleVersionListResponse,
    summary="List all rule versions",
)
async def list_rules(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    total = (await db.execute(select(func.count()).select_from(RuleVersion))).scalar_one()
    versions = (
        await db.execute(
            select(RuleVersion).order_by(RuleVersion.created_at.desc()).offset(skip).limit(limit)
        )
    ).scalars().all()
    items = [RuleVersionListItem.model_validate(v) for v in versions]
    return RuleVersionListResponse(items=items, total=total)


# ─── GET /rules/{id} ───

@router.get(
    "/{version_id}",
    response_model=RuleVersionDetail,
    summary="Get rule version detail with config JSON",
)
async def get_rule(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(get_current_user),
):
    version = await _get_version_or_404(db, version_id)
    return RuleVersionDetail.model_validate(version)


# ─── PATCH /rules/{id} ───

@router.patch(
    "/{version_id}",
    response_model=RuleVersionDetail,
    summary="Update rule version config (human review of AI suggestion)",
)
async def update_rule(
    version_id: uuid.UUID,
    body: RuleVersionUpdate,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(require_role("ADMIN", "AP_ANALYST")),
):
    version = await _get_version_or_404(db, version_id)

    if version.status not in ("draft", "in_review"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit rule version in status '{version.status}'.",
        )

    if body.config_json is not None:
        try:
            json.loads(body.config_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"config_json is not valid JSON: {exc}",
            )
        version.config_json = body.config_json

    if body.change_summary is not None:
        version.change_summary = body.change_summary

    if body.is_shadow_mode is not None:
        version.is_shadow_mode = body.is_shadow_mode

    await db.commit()
    await db.refresh(version)
    return RuleVersionDetail.model_validate(version)


# ─── POST /rules/{id}/publish ───

@router.post(
    "/{version_id}/publish",
    response_model=RuleVersionDetail,
    summary="Publish rule version; supersedes previous published version for the same rule",
)
async def publish_rule(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(require_role("ADMIN")),
):
    version = await _get_version_or_404(db, version_id)

    if version.status not in ("draft", "in_review"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot publish rule version in status '{version.status}'.",
        )

    # Supersede any existing published versions for the same parent rule
    prev_published = (
        await db.execute(
            select(RuleVersion).where(
                RuleVersion.rule_id == version.rule_id,
                RuleVersion.status == "published",
                RuleVersion.id != version_id,
            )
        )
    ).scalars().all()
    for prev in prev_published:
        prev.status = "superseded"

    version.status = "published"
    version.published_at = datetime.now(timezone.utc)
    version.reviewed_by = current_user.id

    await db.commit()
    await db.refresh(version)
    return RuleVersionDetail.model_validate(version)


# ─── POST /rules/{id}/reject ───

@router.post(
    "/{version_id}/reject",
    response_model=RuleVersionDetail,
    summary="Reject a rule version",
)
async def reject_rule(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user=Depends(require_role("ADMIN")),
):
    version = await _get_version_or_404(db, version_id)

    if version.status not in ("draft", "in_review"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject rule version in status '{version.status}'.",
        )

    version.status = "rejected"
    version.reviewed_by = current_user.id

    await db.commit()
    await db.refresh(version)
    return RuleVersionDetail.model_validate(version)


# ─── Helper ───

async def _get_version_or_404(db: AsyncSession, version_id: uuid.UUID) -> RuleVersion:
    version = await db.get(RuleVersion, version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule version not found.")
    return version
