"""Seed script — creates initial admin user and sample data for dev."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password as get_password_hash
from app.models.user import User
from app.models.vendor import Vendor


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as db:
        # Admin user
        admin = User(
            email="admin@example.com",
            name="Admin User",
            password_hash=get_password_hash("changeme123"),
            role="ADMIN",
            is_active=True,
        )
        db.add(admin)

        # AP Clerk
        clerk = User(
            email="clerk@example.com",
            name="AP Clerk",
            password_hash=get_password_hash("changeme123"),
            role="AP_CLERK",
            is_active=True,
        )
        db.add(clerk)

        # Sample vendor
        vendor = Vendor(
            name="Acme Corp",
            tax_id="12-3456789",
            currency="USD",
            payment_terms=30,
            email="ap@acmecorp.example.com",
            is_active=True,
        )
        db.add(vendor)

        await db.commit()
        print("Seed complete.")
        print("  admin@example.com / changeme123")
        print("  clerk@example.com / changeme123")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
