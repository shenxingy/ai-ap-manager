"""Simple FX conversion service for normalizing invoice amounts to USD."""
from decimal import Decimal

# Static mid-market rates (replace with live API in production)
RATES: dict[str, Decimal] = {
    "USD": Decimal("1.0"),
    "EUR": Decimal("1.08"),
    "GBP": Decimal("1.27"),
    "CAD": Decimal("0.74"),
    "AUD": Decimal("0.65"),
    "JPY": Decimal("0.0067"),
    "CNY": Decimal("0.14"),
    "INR": Decimal("0.012"),
    "MXN": Decimal("0.058"),
    "CHF": Decimal("1.13"),
}


def convert_to_usd(amount: Decimal, currency: str) -> Decimal:
    """Convert an amount from the given currency to USD.

    Falls back to 1:1 for unknown currencies (assumes USD-equivalent).
    """
    rate = RATES.get(currency.upper(), Decimal("1.0"))
    return (amount * rate).quantize(Decimal("0.0001"))
