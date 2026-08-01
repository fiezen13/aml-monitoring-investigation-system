"""Static FX rates to USD (FIN-07 Task 1). Versioned for reproducibility.

Rates are approximate spot placeholders for synthetic IBM AML data so thresholds
can be computed in one unit. DQ sum checks use original currency amounts, not USD.

IBM LI-Small uses full names (e.g. 'US Dollar'), not ISO codes.
"""

from __future__ import annotations

FX_VERSION = "2026-07-31-static-v2"

# 1 unit of currency = rate USD
_ISO_RATES: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "JPY": 0.0067,
    "CAD": 0.74,
    "AUD": 0.66,
    "CHF": 1.12,
    "CNY": 0.14,
    "HKD": 0.13,
    "SGD": 0.74,
    "INR": 0.012,
    "BRL": 0.18,
    "MXN": 0.059,
    "ZAR": 0.055,
    "RUB": 0.011,
    "TRY": 0.031,
    "SAR": 0.27,
    "AED": 0.27,
    "SEK": 0.095,
    "NOK": 0.093,
    "DKK": 0.145,
    "NZD": 0.61,
    "KRW": 0.00074,
    "TWD": 0.031,
    "THB": 0.028,
    "MYR": 0.21,
    "IDR": 0.000063,
    "PHP": 0.017,
    "VND": 0.000040,
    "PLN": 0.25,
    "CZK": 0.043,
    "HUF": 0.0027,
    "ILS": 0.27,
    "BTC": 60_000.0,
}

# IBM AML dataset full names → ISO
_IBM_NAME_TO_ISO: dict[str, str] = {
    "US Dollar": "USD",
    "Euro": "EUR",
    "UK Pound": "GBP",
    "Yen": "JPY",
    "Canadian Dollar": "CAD",
    "Australian Dollar": "AUD",
    "Swiss Franc": "CHF",
    "Yuan": "CNY",
    "Rupee": "INR",
    "Brazil Real": "BRL",
    "Mexican Peso": "MXN",
    "Ruble": "RUB",
    "Saudi Riyal": "SAR",
    "Shekel": "ILS",
    "Bitcoin": "BTC",
}

FX_TO_USD: dict[str, float] = dict(_ISO_RATES)
FX_TO_USD.update({name: _ISO_RATES[iso] for name, iso in _IBM_NAME_TO_ISO.items()})
FX_TO_USD["BITCOIN"] = _ISO_RATES["BTC"]
FX_TO_USD["Bitcoin"] = _ISO_RATES["BTC"]


class UnknownCurrencyError(ValueError):
    pass


def normalize_currency(currency: str) -> str:
    """Return canonical FX map key for a raw currency string."""
    key = str(currency).strip()
    if key in FX_TO_USD:
        return key
    upper = key.upper()
    if upper in FX_TO_USD:
        return upper
    # case-insensitive match for IBM full names
    lower_map = {k.lower(): k for k in FX_TO_USD}
    if key.lower() in lower_map:
        return lower_map[key.lower()]
    raise UnknownCurrencyError(f"No FX rate for currency={currency!r} (FX {FX_VERSION})")


def to_usd(amount: float, currency: str) -> float:
    key = normalize_currency(currency)
    return float(amount) * FX_TO_USD[key]
