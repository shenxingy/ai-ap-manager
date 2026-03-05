"""FX rate fetch Celery task.

Fetches daily exchange rates from ECB (European Central Bank) XML feed,
derives USD-base rates, and upserts into fx_rates table.

ECB publishes rates relative to EUR; we cross-convert to produce
USD-based pairs (e.g. USD/EUR, USD/GBP, USD/JPY, …).
"""
import logging
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
ECB_NS = "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"


def _get_sync_session():
    """Return a sync SQLAlchemy session. Caller must close it."""
    engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return Session()


def _fetch_ecb_rates() -> tuple[date, dict[str, float]]:
    """Fetch ECB XML and return (valid_date, {currency: rate_vs_eur})."""
    with urllib.request.urlopen(ECB_URL, timeout=15) as resp:
        xml_bytes = resp.read()
    root = ET.fromstring(xml_bytes)
    # Navigate to the Cube element that has time attribute
    cube_with_time = root.find(f".//{ECB_NS}Cube[@time]")
    if cube_with_time is None:
        raise ValueError("ECB XML: could not find Cube[@time] element")
    valid_date = date.fromisoformat(cube_with_time.attrib["time"])
    rates: dict[str, float] = {"EUR": 1.0}  # base is EUR
    for child in cube_with_time:
        currency = child.attrib.get("currency")
        rate_str = child.attrib.get("rate")
        if currency and rate_str:
            rates[currency] = float(rate_str)
    return valid_date, rates


def _build_usd_pairs(rates: dict[str, float]) -> list[dict]:
    """Convert EUR-based rates to USD-based pairs.

    ECB rates are quote vs EUR (e.g. USD=1.08 means 1 EUR = 1.08 USD).
    We want base=USD, so: USD→EUR = 1/USD_rate, USD→XXX = XXX_rate/USD_rate.
    """
    usd_rate = rates.get("USD")
    if not usd_rate:
        raise ValueError("USD not found in ECB rates — cannot build USD-base pairs")
    pairs = []
    for quote, eur_rate in rates.items():
        if quote == "USD":
            continue
        usd_to_quote = eur_rate / usd_rate  # how many quote per 1 USD
        pairs.append({"base": "USD", "quote": quote, "rate": usd_to_quote})
    # Also add EUR itself
    pairs.append({"base": "USD", "quote": "EUR", "rate": 1.0 / usd_rate})
    return pairs


@celery_app.task(name="app.workers.fx_tasks.fetch_fx_rates")
def fetch_fx_rates():
    """Fetch ECB daily FX rates and upsert into fx_rates table.

    Returns dict with status and count of upserted rows.
    """
    db = _get_sync_session()
    try:
        valid_date, ecb_rates = _fetch_ecb_rates()
        pairs = _build_usd_pairs(ecb_rates)
        fetched_at = datetime.now(UTC)
        upserted = 0
        for pair in pairs:
            db.execute(text("""
                INSERT INTO fx_rates (base_currency, quote_currency, rate, valid_date, source, fetched_at)
                VALUES (:base, :quote, :rate, :vdate, :src, :fat)
                ON CONFLICT (base_currency, quote_currency, valid_date) DO UPDATE SET
                    rate = EXCLUDED.rate,
                    source = EXCLUDED.source,
                    fetched_at = EXCLUDED.fetched_at
            """), {
                "base": pair["base"],
                "quote": pair["quote"],
                "rate": pair["rate"],
                "vdate": valid_date,
                "src": settings.FX_RATES_SOURCE,
                "fat": fetched_at,
            })
            upserted += 1

        db.commit()
        logger.info("FX rates fetch complete: %d pairs upserted for %s", upserted, valid_date)
        return {"status": "ok", "pairs_upserted": upserted, "valid_date": str(valid_date)}

    except Exception as e:
        db.rollback()
        logger.error("FX rates fetch failed: %s", e)
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
