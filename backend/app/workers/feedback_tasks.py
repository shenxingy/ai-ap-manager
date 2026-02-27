"""Celery tasks for AI feedback analysis and rule recommendations."""
import logging
from datetime import datetime, timedelta, timezone

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.feedback_tasks.analyze_ai_feedback", bind=True)
def analyze_ai_feedback(self):
    """Analyze AI correction patterns and generate rule recommendations.

    Runs weekly (Sunday midnight UTC). Looks at corrections in the past 7 days,
    identifies patterns, and creates RuleRecommendation records for admin review.
    """
    logger.info("analyze_ai_feedback: starting weekly analysis")
    try:
        from sqlalchemy import create_engine, func, select
        from sqlalchemy.orm import sessionmaker
        from app.core.config import settings
        from app.models.feedback import AiFeedback, RuleRecommendation

        engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        Session = sessionmaker(bind=engine, expire_on_commit=False)

        with Session() as db:
            since = datetime.now(timezone.utc) - timedelta(days=7)
            period_end = datetime.now(timezone.utc)

            # Count corrections by type and field
            corrections = db.execute(
                select(
                    AiFeedback.feedback_type,
                    AiFeedback.field_name,
                    func.count(AiFeedback.id).label("cnt"),
                )
                .where(AiFeedback.created_at >= since)
                .group_by(AiFeedback.feedback_type, AiFeedback.field_name)
                .order_by(func.count(AiFeedback.id).desc())
            ).all()

            total_corrections = sum(row.cnt for row in corrections)
            if total_corrections == 0:
                logger.info("analyze_ai_feedback: no corrections in past 7 days, skipping")
                return {"status": "skipped", "reason": "no_corrections"}

            # Field corrections: group by field_name for tolerance rule suggestions
            field_corrections = [r for r in corrections if r.feedback_type == "field_correction"]
            gl_corrections = [r for r in corrections if r.feedback_type == "gl_correction"]
            exc_corrections = [r for r in corrections if r.feedback_type == "exception_correction"]

            recommendations_created = 0

            # Suggest tolerance rule update if total_amount or unit_price has many corrections
            amount_fields = {"total_amount", "unit_price", "subtotal"}
            high_amount_corrections = sum(
                r.cnt for r in field_corrections if r.field_name in amount_fields
            )
            if high_amount_corrections >= 5:
                rec = RuleRecommendation(
                    rule_type="tolerance",
                    title=f"Adjust amount tolerance — {high_amount_corrections} corrections in 7 days",
                    description=(
                        f"The system recorded {high_amount_corrections} corrections to amount fields "
                        f"(total_amount, unit_price, subtotal) in the past week. "
                        "This pattern suggests the current matching tolerance thresholds may be too strict, "
                        "causing false exception flags. Consider reviewing the tolerance_pct setting."
                    ),
                    evidence_summary=f"Amount field corrections: {high_amount_corrections} in 7 days",
                    suggested_config='{"tolerance_pct": 3.0}',
                    confidence_score=min(0.9, high_amount_corrections / 20),
                    status="pending",
                    analysis_period_start=since,
                    analysis_period_end=period_end,
                    correction_count=high_amount_corrections,
                )
                db.add(rec)
                recommendations_created += 1

            # Suggest GL mapping rule if GL corrections are high
            if sum(r.cnt for r in gl_corrections) >= 10:
                total_gl = sum(r.cnt for r in gl_corrections)
                rec = RuleRecommendation(
                    rule_type="gl_mapping",
                    title=f"Review GL auto-coding — {total_gl} overrides in 7 days",
                    description=(
                        f"Users overrode GL account suggestions {total_gl} times in the past week. "
                        "This indicates the frequency-based GL suggestion model is not well-calibrated "
                        "for recent transactions. Consider retraining with recent GL assignments or "
                        "adding vendor-specific GL mappings."
                    ),
                    evidence_summary=f"GL overrides: {total_gl} in 7 days",
                    suggested_config=None,
                    confidence_score=min(0.85, total_gl / 30),
                    status="pending",
                    analysis_period_start=since,
                    analysis_period_end=period_end,
                    correction_count=total_gl,
                )
                db.add(rec)
                recommendations_created += 1

            # Suggest routing rule update if many exceptions were reassigned
            if sum(r.cnt for r in exc_corrections) >= 5:
                total_exc = sum(r.cnt for r in exc_corrections)
                rec = RuleRecommendation(
                    rule_type="routing",
                    title=f"Review exception routing — {total_exc} status changes in 7 days",
                    description=(
                        f"The system recorded {total_exc} exception status corrections in the past week. "
                        "Frequent exception reopening or reassignment may indicate routing rules "
                        "are sending exceptions to incorrect teams. Review ExceptionRoutingRule configurations."
                    ),
                    evidence_summary=f"Exception corrections: {total_exc} in 7 days",
                    suggested_config=None,
                    confidence_score=min(0.75, total_exc / 20),
                    status="pending",
                    analysis_period_start=since,
                    analysis_period_end=period_end,
                    correction_count=total_exc,
                )
                db.add(rec)
                recommendations_created += 1

            db.commit()
            logger.info(
                "analyze_ai_feedback: created %d recommendations from %d corrections",
                recommendations_created, total_corrections,
            )
            return {
                "status": "complete",
                "total_corrections": total_corrections,
                "recommendations_created": recommendations_created,
            }

    except Exception as exc:
        logger.exception("analyze_ai_feedback failed: %s", exc)
        raise self.retry(exc=exc, countdown=3600, max_retries=2)
