"""Seed default data into the database."""
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.exception_routing import ExceptionRoutingRule

logger = logging.getLogger(__name__)

# Default routing rules: (exception_code, target_role, priority)
DEFAULT_ROUTING_RULES = [
    ("PRICE_VARIANCE", "AP_ANALYST", 0),
    ("MISSING_PO", "AP_ANALYST", 0),
    ("FRAUD_FLAG", "ADMIN", 10),
    ("QTY_VARIANCE", "AP_ANALYST", 0),
    ("QTY_OVER_RECEIPT", "AP_ANALYST", 0),
    ("GRN_NOT_FOUND", "AP_ANALYST", 0),
]


async def seed_exception_routing_rules(db: AsyncSession) -> None:
    """Upsert default exception routing rules (insert if not exists by exception_code)."""
    for exception_code, target_role, priority in DEFAULT_ROUTING_RULES:
        existing = await db.execute(
            select(ExceptionRoutingRule).where(
                ExceptionRoutingRule.exception_code == exception_code
            )
        )
        if existing.scalars().first() is None:
            rule = ExceptionRoutingRule(
                exception_code=exception_code,
                target_role=target_role,
                priority=priority,
                is_active=True,
            )
            db.add(rule)
            logger.info("Seeded routing rule: %s -> %s", exception_code, target_role)
        else:
            logger.info("Routing rule already exists: %s, skipping", exception_code)

    await db.commit()


async def run_seed() -> None:
    async with AsyncSessionLocal() as db:
        await seed_exception_routing_rules(db)
    logger.info("Seeding complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_seed())
