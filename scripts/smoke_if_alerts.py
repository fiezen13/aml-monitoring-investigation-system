#!/usr/bin/env python3
"""STEP 3 smoke: IF alerts visible in Postgres + API list.

Ví dụ:
  python scripts/smoke_if_alerts.py
  python scripts/smoke_if_alerts.py --api-base http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from src.db.session import get_session  # noqa: E402


def _http_get_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_db() -> dict:
    with get_session() as session:
        n_ml = session.execute(
            text(
                """
                SELECT count(*) FROM alert
                 WHERE detector = 'ml' AND alert_id LIKE 'ALT-IF-%'
                """
            )
        ).scalar_one()
        thin = session.execute(
            text(
                """
                SELECT count(*) FROM (
                    SELECT a.alert_id
                      FROM alert a
                      LEFT JOIN alert_reason r ON r.alert_id = a.alert_id
                     WHERE a.alert_id LIKE 'ALT-IF-%'
                     GROUP BY a.alert_id
                    HAVING count(r.alert_reason_id) < 3
                ) t
                """
            )
        ).scalar_one()
        missing = session.execute(
            text(
                """
                SELECT count(*) FROM alert al
                LEFT JOIN account ac ON ac.account_key = al.account_key
                LEFT JOIN customer c ON c.customer_id = ac.customer_id
                WHERE al.alert_id LIKE 'ALT-IF-%'
                  AND c.customer_id IS NULL
                """
            )
        ).scalar_one()
        sample = (
            session.execute(
                text(
                    """
                    SELECT alert_id, account_key, risk_score
                      FROM alert
                     WHERE alert_id LIKE 'ALT-IF-%'
                     ORDER BY risk_score DESC
                     LIMIT 3
                    """
                )
            )
            .mappings()
            .all()
        )
    return {
        "n_ml_alerts": int(n_ml),
        "n_thin_reasons": int(thin),
        "n_missing_customer": int(missing),
        "sample": [dict(r) for r in sample],
        "pass": int(n_ml) > 0 and int(thin) == 0 and int(missing) == 0,
    }


def check_api(api_base: str) -> dict:
    base = api_base.rstrip("/")
    out: dict = {
        "api_base": base,
        "list_ok": False,
        "ml_seen": False,
        "detail_ok": None,
        "dashboard_ok": None,
        "notes": [],
    }
    try:
        payload = _http_get_json(f"{base}/api/v1/alerts?limit=50")
    except urllib.error.HTTPError as exc:
        out["notes"].append(f"GET /api/v1/alerts failed: HTTP {exc.code}")
        out["pass"] = False
        return out
    except Exception as exc:  # noqa: BLE001
        out["notes"].append(f"GET /api/v1/alerts failed: {exc}")
        out["pass"] = False
        return out

    out["list_ok"] = True
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        rows = payload["data"]
        out["notes"].append("API wraps alerts in {success,total,data} (slim stack)")
    else:
        out["notes"].append(f"Unexpected alerts payload type: {type(payload)}")
        out["pass"] = False
        return out

    ml_rows = [
        r
        for r in rows
        if isinstance(r, dict)
        and (r.get("detector") == "ml" or str(r.get("alert_id", "")).startswith("ALT-IF-"))
    ]
    out["ml_seen"] = len(ml_rows) > 0
    out["list_ml_rows"] = len(ml_rows)
    if not ml_rows:
        out["notes"].append("No ml/ALT-IF rows in first page of /alerts")
        out["pass"] = False
        return out

    sample_id = str(ml_rows[0]["alert_id"])
    out["sample_alert_id"] = sample_id
    try:
        detail = _http_get_json(f"{base}/api/v1/alerts/{urllib.parse.quote(sample_id)}")
        out["detail_ok"] = True
        if isinstance(detail, dict):
            reasons = detail.get("reasons")
            out["detail_reason_count"] = len(reasons) if isinstance(reasons, list) else None
            out["detail_has_customer"] = "customer" in detail
    except urllib.error.HTTPError as exc:
        out["detail_ok"] = False
        out["notes"].append(
            f"GET /api/v1/alerts/{{id}} HTTP {exc.code} — stack may only expose list endpoint"
        )
    except Exception as exc:  # noqa: BLE001
        out["detail_ok"] = False
        out["notes"].append(f"detail error: {exc}")

    try:
        _http_get_json(f"{base}/api/v1/dashboard")
        out["dashboard_ok"] = True
    except urllib.error.HTTPError as exc:
        out["dashboard_ok"] = False
        out["notes"].append(f"GET /api/v1/dashboard HTTP {exc.code} (optional on slim API)")
    except Exception as exc:  # noqa: BLE001
        out["dashboard_ok"] = False
        out["notes"].append(f"dashboard error: {exc}")

    out["pass"] = bool(out["list_ok"] and out["ml_seen"])
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Smoke test IF alerts in DB + API")
    p.add_argument("--api-base", default="http://localhost:8000")
    p.add_argument("--skip-api", action="store_true")
    args = p.parse_args()

    print("[1/2] DB checks ...", flush=True)
    db = check_db()
    print(json.dumps({"db": db}, ensure_ascii=False, indent=2, default=str), flush=True)

    api: dict = {"skipped": True, "pass": True}
    if not args.skip_api:
        print("[2/2] API checks ...", flush=True)
        api = check_api(args.api_base)
        print(json.dumps({"api": api}, ensure_ascii=False, indent=2), flush=True)
    else:
        print("[2/2] API skipped", flush=True)

    ok = bool(db.get("pass")) and bool(api.get("pass"))
    print("SMOKE " + ("PASS" if ok else "FAIL"), flush=True)
    print("UI manual: http://localhost:5173/alerts", flush=True)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
