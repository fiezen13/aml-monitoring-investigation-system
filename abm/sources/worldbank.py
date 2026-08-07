"""Acquire Vietnamese population and financial-inclusion statistics.

Phase 5 exists because of one rule: **no percentage may be typed into Python from
memory or from reading a report.** Every number that shapes the synthetic
population has to arrive through code, from a named source, with the response
kept on disk and checksummed, so a reviewer can re-fetch it and get the same
thing.

The World Bank open data API is used because it serves Vietnamese data from two
authorities in a machine-readable, versioned, citable form:

- **Global Findex** (source 28) — the World Bank's own nationally representative
  survey. This is the primary source, not a proxy.
- **World Development Indicators** (source 2) — population structure from the UN
  World Population Prospects, and labour-force series from ILO modelled
  estimates.

What this does *not* cover, and must not be pretended otherwise: Vietnamese
sub-national regions, enterprise size and turnover distributions, and declared
KYC income. Those need the National Statistics Office directly, and until they
are acquired the affected parameters stay marked as assumptions.

Findex publishes each indicator broken down one dimension at a time — by sex, by
age, by income group, by urban/rural, by labour-force status — but never as a
joint table. Combining them therefore requires an explicit assumption, which is
made and labelled in `vn_distributions.py` rather than hidden here.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

API_ROOT = "https://api.worldbank.org/v2"
COUNTRY = "VNM"
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "P022-ABM-source-acquisition/0.1"

# Space out requests so a full acquisition does not look like an attack.
REQUEST_SPACING_SECONDS = 0.15

# Suffixes Findex appends to an indicator for each published breakdown.
FINDEX_BREAKDOWNS: dict[str, tuple[str, str]] = {
    "": ("all", "all"),
    ".1": ("gender", "F"),
    ".2": ("gender", "M"),
    ".3": ("age_band", "15-24"),
    ".4": ("age_band", "25+"),
    ".5": ("education", "PRIMARY_OR_LESS"),
    ".6": ("education", "SECONDARY_OR_MORE"),
    ".7": ("income_group", "POOREST_40"),
    ".8": ("income_group", "RICHEST_60"),
    ".9": ("urban_rural", "RURAL"),
    ".10": ("urban_rural", "URBAN"),
    ".11": ("labour_force", "OUT_OF_LABOUR_FORCE"),
    ".12": ("labour_force", "IN_LABOUR_FORCE"),
}

# Findex behaviors the KYC model needs. Key is the name used downstream.
FINDEX_INDICATORS: dict[str, str] = {
    "account_ownership": "account.t.d",
    "digital_payment": "g20.any",
    "formal_saving": "fin17a.17a1.d",
    "borrowed_any": "borrow.any.t.d",
    "mobile_money_account": "mobileaccount.t.d",
    "mobile_phone_ownership": "con1",
    "wages_into_account": "fin32.n33.acc",
    # Denominator is wage recipients, not all adults. That is the conditional the
    # KYC generator actually needs, since it only asks the question of wage
    # workers; the "% of all adults" version would undershoot once gated.
    "wages_into_account_given_wages": "fin32.n33.acc.s",
}

# Five-year population bands, published as a share of that sex's population.
_AGE_BANDS = (
    "1519",
    "2024",
    "2529",
    "3034",
    "3539",
    "4044",
    "4549",
    "5054",
    "5559",
    "6064",
    "6569",
    "7074",
    "7579",
    "80UP",
)

WDI_INDICATORS: dict[str, str] = {
    "population_total": "SP.POP.TOTL",
    "population_male": "SP.POP.TOTL.MA.IN",
    "population_female": "SP.POP.TOTL.FE.IN",
    "urban_population_share": "SP.URB.TOTL.IN.ZS",
    "labour_force_participation": "SL.TLF.CACT.ZS",
    "employment_wage_salaried": "SL.EMP.WORK.ZS",
    "employment_self_employed": "SL.EMP.SELF.ZS",
    "employment_employers": "SL.EMP.MPYR.ZS",
    "employment_family_workers": "SL.FAM.WORK.ZS",
    "employment_agriculture": "SL.AGR.EMPL.ZS",
    "employment_industry": "SL.IND.EMPL.ZS",
    "employment_services": "SL.SRV.EMPL.ZS",
    "income_share_q1": "SI.DST.FRST.20",
    "income_share_q2": "SI.DST.02ND.20",
    "income_share_q3": "SI.DST.03RD.20",
    "income_share_q4": "SI.DST.04TH.20",
    "income_share_q5": "SI.DST.05TH.20",
    "gini": "SI.POV.GINI",
    "gni_per_capita_usd": "NY.GNP.PCAP.CD",
    "gdp_per_capita_usd": "NY.GDP.PCAP.CD",
    # In current local currency, so the monetary anchor needs no FX conversion
    # and inherits no exchange-rate assumption.
    "gdp_per_capita_vnd": "NY.GDP.PCAP.CN",
    "exchange_rate_vnd_per_usd": "PA.NUS.FCRF",
    "unemployment_rate": "SL.UEM.TOTL.ZS",
    "new_business_density": "IC.BUS.NDNS.ZS",
    "inflation_cpi_percent": "FP.CPI.TOTL.ZG",
    # Findex splits education at "primary or less" versus "secondary or more",
    # and that split carries its strongest conditional signal by far. This is the
    # matching marginal: the share of adults with at least lower secondary.
    "education_lower_secondary_or_more": "SE.SEC.CUAT.LO.ZS",
    "education_upper_secondary_or_more": "SE.SEC.CUAT.UP.ZS",
    "education_tertiary_bachelor": "SE.TER.CUAT.BA.ZS",
    # World Bank Enterprise Surveys, Viet Nam 2023. These describe firm banking
    # behavior, which is what the business KYC model needs; they do NOT give the
    # firm size or turnover distribution, which stays an assumption.
    "firms_with_bank_credit": "IC.FRM.BNKS.ZS",
    "firms_using_banks_for_working_capital": "IC.FRM.BKWC.ZS",
    "firms_with_female_ownership": "IC.FRM.FEMO.ZS",
    "firms_competing_against_informal": "IC.FRM.CMPU.ZS",
}

AGE_INDICATORS: dict[str, str] = {
    f"population_age_{band}_{sex.lower()}": f"SP.POP.{band}.{sex}.5Y" for band in _AGE_BANDS for sex in ("MA", "FE")
}


class SourceUnavailableError(RuntimeError):
    """The API could not be reached. Callers must not substitute a guess."""


def _get_with_retry(url: str, *, label: str, attempts: int = 4) -> str:
    """GET with backoff.

    Acquiring the full set is roughly 140 requests, and the API answers a burst
    with HTTP 400 rather than 429 — a transient rejection that looks exactly like
    a malformed request. Retrying with backoff is what separates "the API is
    busy" from "this indicator does not exist", and getting that wrong would
    silently drop a real indicator from the profile.
    """
    delay = 1.0
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                time.sleep(REQUEST_SPACING_SECONDS)
                return response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == attempts:
                raise SourceUnavailableError(f"could not fetch {label}: {exc}") from exc
            time.sleep(delay)
            delay *= 2
    raise SourceUnavailableError(f"could not fetch {label}")


def _cache_path(cache_dir: Path, indicator: str) -> Path:
    # Indicator IDs contain dots and would otherwise produce confusing suffixes.
    return cache_dir / f"{indicator.replace('.', '_')}.json"


def fetch_indicator(indicator: str, *, cache_dir: Path, refresh: bool = False) -> list[dict[str, Any]]:
    """Fetch one indicator's full Vietnam series, caching the raw response.

    The cached file is the evidence. It is written verbatim, never normalized,
    so its checksum can be compared against a re-fetch.
    """
    path = _cache_path(cache_dir, indicator)
    if path.exists() and not refresh:
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        body = _get_with_retry(
            f"{API_ROOT}/country/{COUNTRY}/indicator/{indicator}?format=json&per_page=200",
            label=indicator,
        )
        payload = json.loads(body)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        return []
    return payload[1]


def latest_observation(series: list[dict[str, Any]]) -> tuple[int, float] | None:
    """The most recent non-null point, with its year.

    Returning the year alongside the value is not decoration. Findex is a
    four-yearly survey and population figures are annual, so a derived parameter
    that mixes them must be able to state which year each input came from.
    """
    points = [
        (int(row["date"]), float(row["value"])) for row in series if row.get("value") is not None and row.get("date")
    ]
    return max(points, key=lambda point: point[0]) if points else None


def acquire(cache_dir: Path, *, refresh: bool = False) -> dict[str, Any]:
    """Fetch everything and return a provenance record.

    Indicators with no Vietnamese data are recorded as unavailable rather than
    dropped, because a later reader needs to know the difference between "not
    requested" and "requested and not published".
    """
    started = datetime.now(UTC)
    acquired: dict[str, Any] = {}
    unavailable: list[str] = []

    groups = {
        "findex": _findex_indicator_ids(),
        "wdi": WDI_INDICATORS,
        "population_age": AGE_INDICATORS,
    }
    for group, indicators in groups.items():
        for alias, indicator in indicators.items():
            series = fetch_indicator(indicator, cache_dir=cache_dir, refresh=refresh)
            latest = latest_observation(series)
            if latest is None:
                unavailable.append(f"{alias} ({indicator})")
                continue
            year, value = latest
            acquired[alias] = {
                "group": group,
                "indicator": indicator,
                "year": year,
                "value": value,
                "observations": len(series),
            }

    return {
        "acquired_at": started.isoformat(timespec="seconds"),
        "api_root": API_ROOT,
        "country": COUNTRY,
        "indicators_acquired": len(acquired),
        "indicators_unavailable": unavailable,
        "cache_dir": str(cache_dir),
        "cache_checksums": _checksums(cache_dir),
        "values": acquired,
    }


def _findex_indicator_ids() -> dict[str, str]:
    return {
        f"{name}{'' if suffix == '' else '__' + suffix.lstrip('.')}": f"{base}{suffix}"
        for name, base in FINDEX_INDICATORS.items()
        for suffix in FINDEX_BREAKDOWNS
    }


def _checksums(cache_dir: Path) -> dict[str, str]:
    if not cache_dir.exists():
        return {}
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()[:16] for path in sorted(cache_dir.glob("*.json"))}


def findex_breakdown(values: dict[str, Any], behavior: str) -> dict[str, Any]:
    """Reshape one Findex behavior into its published breakdowns.

    Returns the overall rate plus, per dimension, the rate for each category.
    Every rate is a percentage of adults aged 15 and over.
    """
    overall = values.get(behavior)
    dimensions: dict[str, dict[str, Any]] = {}
    for suffix, (dimension, category) in FINDEX_BREAKDOWNS.items():
        if suffix == "":
            continue
        entry = values.get(f"{behavior}__{suffix.lstrip('.')}")
        if entry is None:
            continue
        dimensions.setdefault(dimension, {})[category] = {
            "rate_percent": entry["value"],
            "year": entry["year"],
        }
    return {
        "behavior": behavior,
        "overall_rate_percent": overall["value"] if overall else None,
        "year": overall["year"] if overall else None,
        "by_dimension": dimensions,
    }
