"""Map Isolation Forest scores → ``aml.detection.result.v1`` payloads.

Không tạo alert. Alert aggregation (fusion) consume các kết quả này sau.
Dùng chung bởi ``scripts/emit_if_detection_results.py``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
TOPIC = "aml.detection.result.v1"
DETECTOR_ID = "isolation_forest_account_behavior"
DETECTOR_TYPE = "ML_UNSUPERVISED"
FEATURE_SET_ID = "account_behavior_if_20"
FEATURE_DEFINITION_VERSION = "feature_spec_v1"
DEFAULT_THRESHOLD = 0.70
DEFAULT_TYPOLOGY = "T02"

FEATURE_LABELS: dict[str, str] = {
    "txn_count": "Tong so giao dich trong cua so",
    "incoming_count": "So giao dich nhan",
    "outgoing_count": "So giao dich gui",
    "active_days": "So ngay co phat sinh giao dich",
    "txn_per_active_day": "Mat do giao dich tren ngay hoat dong",
    "total_inflow": "Tong tien vao (log1p USD)",
    "total_outflow": "Tong tien ra (log1p USD)",
    "net_flow": "Dong tien rong (log1p)",
    "outflow_inflow_ratio": "Ty le tien ra / tien vao",
    "rapid_outflow_ratio": "Ty le rut nhanh sau khi nhan (<=2h)",
    "median_dwell_time": "Thoi gian luu tien trung vi (gio)",
    "unique_in_counterparties": "So doi tac gui rieng biet",
    "unique_out_counterparties": "So doi tac nhan rieng biet",
    "new_counterparty_ratio": "Ty le doi tac moi",
    "median_amount": "Trung vi so tien (log1p)",
    "p90_amount": "Phan vi 90% so tien (log1p)",
    "amount_std": "Do lech chuan so tien (log1p)",
    "repeated_amount_ratio": "Ty le giao dich dung so tien lap lai",
    "median_inter_txn_gap": "Khoang cach trung vi giua cac TX (phut)",
    "p10_inter_txn_gap": "Phan vi 10% khoang cach TX (phut)",
}

_CONTRACTS_ROOT = Path(__file__).resolve().parents[2] / "contracts"
_SCHEMA_PATH = _CONTRACTS_ROOT / "events" / "aml.detection.result.v1.schema.json"
_validator = None


def stable_result_id(account_key: str, as_of_ts: Any, window: str, model_version: str) -> str:
    raw = f"{account_key}|{as_of_ts}|{window}|{model_version}|if"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"DR-IF-{digest}"


def _to_rfc3339(value: Any) -> str:
    if isinstance(value, str):
        text = value.strip().replace(" ", "T")
        if text.endswith("+00:00"):
            text = text[:-6] + "Z"
        if re.search(r"(Z|[+-]\d{2}:\d{2})$", text):
            return text
        return text + "Z"

    if isinstance(value, datetime):
        dt = value
    elif hasattr(value, "to_pydatetime"):
        dt = value.to_pydatetime()
    else:
        dt = datetime.now(tz=UTC)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)

    if dt.microsecond:
        # Milliseconds keep payloads compact while staying RFC 3339.
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_top_features(raw: Any) -> list[dict[str, Any]]:
    if raw is None or (isinstance(raw, float) and raw != raw):  # NaN
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, str):
        text = raw.strip()
        if not text or text == "[]":
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    return []


def reason_code_from_feature(feature: str) -> str:
    code = re.sub(r"[^A-Za-z0-9_]", "_", feature).upper()
    code = re.sub(r"_+", "_", code).strip("_")
    if len(code) < 3:
        code = f"IF_{code or 'UNK'}"
    return code[:64]


def _reason_codes_from_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    items = _parse_top_features(row.get("top_anomalous_features"))
    scored: list[tuple[str, str, float, str]] = []
    seen: set[str] = set()

    for item in items:
        feat = str(item.get("feature", "")).strip()
        if not feat or feat in seen:
            continue
        seen.add(feat)
        pct = float(item.get("percentile", 50))
        salience = abs(pct - 50.0)
        label = FEATURE_LABELS.get(feat, f"IF feature: {feat}")
        scored.append((reason_code_from_feature(feat), label, salience, feat))

    if not scored:
        scored.append(
            (
                "IF_ANOMALY_SCORE",
                "Isolation Forest anomaly score (no top features)",
                50.0,
                "anomaly_score",
            )
        )

    total = sum(s for _, _, s, _ in scored) or 1.0
    reasons: list[dict[str, Any]] = []
    for code, label, salience, feat in scored[:12]:
        reasons.append(
            {
                "code": code,
                "description": label[:512],
                "contribution": round(salience / total, 4),
                "feature_refs": [feat[:128]],
            }
        )
    return reasons


def build_detection_result(
    row: dict[str, Any],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    typology_code: str = DEFAULT_TYPOLOGY,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build one contract payload from an IF score row (dict-like)."""
    account_key = str(row["account_key"])
    window = str(row.get("window") or "7d")
    model_version = str(row.get("model_version") or "if_baseline_7d_v1")
    as_of_raw = row.get("as_of_ts")
    score = float(row["anomaly_score"])
    score = min(max(score, 0.0), 1.0)
    thr = float(threshold)
    evaluated = evaluated_at or datetime.now(tz=UTC)
    as_of = _to_rfc3339(as_of_raw)
    result_id = stable_result_id(account_key, as_of_raw, window, model_version)

    # IF score khong calibrated → confidence < 1.0, tang nhe theo score.
    confidence = round(min(0.95, max(0.1, 0.4 + 0.5 * score)), 4)

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "result_id": result_id,
        "entity": {"entity_type": "ACCOUNT", "entity_id": account_key[:128]},
        "detector": {
            "detector_id": DETECTOR_ID,
            "detector_type": DETECTOR_TYPE,
            "version": model_version[:64],
        },
        "evaluated_at": _to_rfc3339(evaluated),
        "as_of_time": as_of,
        "score": round(score, 6),
        "confidence": confidence,
        "triggered": bool(score >= thr),
        "threshold": thr,
        "reason_codes": _reason_codes_from_row(row),
        "typology_candidates": [
            {
                "typology_id": typology_code,
                "typology_version": "v1",
                "confidence": round(min(0.85, max(0.2, score)), 4),
            }
        ],
        "feature_refs": [
            {
                "feature_set_id": FEATURE_SET_ID,
                "as_of_time": as_of,
                "definition_version": FEATURE_DEFINITION_VERSION,
            }
        ],
    }
    return payload


def kafka_key(payload: dict[str, Any]) -> str:
    """Partition key = entity_id (architecture §10.2)."""
    return str(payload["entity"]["entity_id"])


def get_validator():
    """Lazy Draft202012Validator with local contract registry."""
    global _validator
    if _validator is not None:
        return _validator

    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    registry = Registry()
    for path in _CONTRACTS_ROOT.rglob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))

    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    _validator = Draft202012Validator(schema, registry=registry)
    return _validator


def validate_detection_result(payload: dict[str, Any]) -> list[str]:
    """Return list of validation error messages (empty = ok)."""
    validator = get_validator()
    return [e.message for e in validator.iter_errors(payload)]
