"""Pha 4 (địa lý) — bản đồ hành lang streaming, gộp từ BRONZE (Parquet), không PG raw.

Trang World Monitor (/world → `_operational_geography`) đọc `edge_country_hub` +
`edge_country_flow` gắn release trạng thái 'reference'. Ở đây gộp giao dịch thô từ
Bronze theo QUỐC GIA (hub) + HÀNH LANG xuyên biên (flow) rồi ghi hai bảng đó — đúng
kiến trúc: raw ở lake, Postgres chỉ giữ kết quả (bản đồ là aggregate/output).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.streaming import bronze

GEO_RELEASE_ID = "REL-STREAM-GEO"

ISO2 = {
    "UK": "GB", "USA": "US", "UAE": "AE", "Turkey": "TR", "Switzerland": "CH", "Pakistan": "PK",
    "Nigeria": "NG", "Spain": "ES", "Germany": "DE", "Italy": "IT", "France": "FR", "Japan": "JP",
    "Morocco": "MA", "Austria": "AT", "Mexico": "MX", "Albania": "AL", "India": "IN", "Netherlands": "NL",
}

_ENSURE_RELEASE = text("""
    INSERT INTO edge_model_release (release_id, model_version, dataset, split, model_sha256,
        scores_sha256, source_database_sha256, threshold, transaction_rows, positive_rows,
        triggered_rows, feature_count, benchmark, policy, status, trained_at)
    VALUES (:rid, 'geo-stream-samld-v1', 'SAML-D (streaming)', 'test',
            repeat('0',64), repeat('0',64), repeat('0',64), 0.0, :tx, :pos, :trig,
            4, '{"note":"Bản đồ hành lang streaming SAML-D"}'::jsonb, '{"branch":"stream_geo"}'::jsonb,
            'reference', now())
    ON CONFLICT (release_id) DO UPDATE SET transaction_rows=EXCLUDED.transaction_rows,
        triggered_rows=EXCLUDED.triggered_rows, positive_rows=EXCLUDED.positive_rows
""")


def _country(series: pd.Series) -> pd.Series:
    raw = series.astype(str).str.split(":", n=1).str[0]
    return raw.map(lambda c: ISO2.get(c, c))


def refresh(session: Any, geo_release_id: str = GEO_RELEASE_ID) -> tuple[int, int]:
    """Gộp Bronze → edge_country_hub/flow. Trả (số hub, số flow)."""
    df = bronze.read_frame("SAML-D")
    if len(df) == 0:
        return 0, 0
    df = df.copy()
    df["fc"] = _country(df["from_account_key"] if "from_account_key" in df else
                        df["from_bank"].astype(str) + ":" + df["from_account"].astype(str))
    df["tc"] = _country(df["to_bank"].astype(str) + ":" + df["to_account"].astype(str))
    df["from_key"] = df["from_bank"].astype(str) + ":" + df["from_account"].astype(str)
    df["to_key"] = df["to_bank"].astype(str) + ":" + df["to_account"].astype(str)
    df["amt"] = pd.to_numeric(df["amount_paid"], errors="coerce").fillna(0.0)

    # danh sách quốc gia hợp lệ (có toạ độ)
    valid = {r[0] for r in session.execute(text("SELECT country_code FROM country_geo")).all()}

    # cảnh báo streaming theo quốc gia (alert.account_key đã ISO)
    al = pd.read_sql(text("SELECT account_key, risk_score FROM alert WHERE alert_id LIKE 'ALT-STREAM-%'"),
                     session.connection())
    al["code"] = al["account_key"].astype(str).str.split(":", n=1).str[0]
    alert_by_c = al.groupby("code").agg(n=("account_key", "size"), mx=("risk_score", "max")) if len(al) else \
        pd.DataFrame(columns=["n", "mx"]).set_index(pd.Index([], name="code"))

    session.execute(_ENSURE_RELEASE, {
        "rid": geo_release_id, "tx": int(len(df)),
        "pos": int(pd.to_numeric(df["is_laundering"], errors="coerce").fillna(0).sum()),
        "trig": int(len(al))})
    session.execute(text("DELETE FROM edge_country_flow WHERE release_id=:r"), {"r": geo_release_id})
    session.execute(text("DELETE FROM edge_country_hub WHERE release_id=:r"), {"r": geo_release_id})

    # HUB: gộp hai phía (gửi/nhận) theo quốc gia.
    out = df[["fc", "from_key", "amt"]].rename(columns={"fc": "code", "from_key": "acct"}).assign(inb=0, outb=1)
    inn = df[["tc", "to_key", "amt"]].rename(columns={"tc": "code", "to_key": "acct"}).assign(inb=1, outb=0)
    sides = pd.concat([out, inn], ignore_index=True)
    hub = sides.groupby("code").agg(entities=("acct", "nunique"), inbound=("inb", "sum"),
                                    outbound=("outb", "sum")).reset_index()
    hub_rows = []
    for _, r in hub.iterrows():
        if r["code"] not in valid:
            continue
        a = alert_by_c.loc[r["code"]] if r["code"] in alert_by_c.index else None
        hub_rows.append({"r": geo_release_id, "c": r["code"], "e": int(r["entities"]),
                         "i": int(r["inbound"]), "o": int(r["outbound"]),
                         "al": int(a["n"]) if a is not None else 0,
                         "rk": float(a["mx"]) if a is not None else 0.0})
    if hub_rows:
        session.execute(text("INSERT INTO edge_country_hub (release_id, country_code, entities, inbound, "
                             "outbound, alerts, risk_score) VALUES (:r,:c,:e,:i,:o,:al,:rk)"), hub_rows)

    # FLOW: hành lang xuyên biên (nước gửi ≠ nước nhận), theo tiền tệ + kênh.
    cross = df[(df["fc"] != df["tc"]) & df["fc"].isin(valid) & df["tc"].isin(valid)]
    flow = cross.groupby(["fc", "tc", "payment_currency", "payment_format"]).agg(
        n=("amt", "size"), vol=("amt", "sum"),
        fs=("event_time", "min"), ls=("event_time", "max")).reset_index()
    flow_rows = [{"r": geo_release_id, "s": x["fc"], "t": x["tc"], "cur": str(x["payment_currency"])[:64],
                  "ch": str(x["payment_format"]), "n": int(x["n"]), "vol": float(x["vol"]),
                  "fs": x["fs"], "ls": x["ls"]} for _, x in flow.iterrows()]
    if flow_rows:
        session.execute(text("INSERT INTO edge_country_flow (release_id, source_country_code, target_country_code, "
                             "currency, channel, txn_count, amount_native, first_seen, last_seen, alert_count, risk_score) "
                             "VALUES (:r,:s,:t,:cur,:ch,:n,:vol,:fs,:ls,0,0)"), flow_rows)

    hubs = session.execute(text("SELECT count(*) FROM edge_country_hub WHERE release_id=:r"), {"r": geo_release_id}).scalar()
    flows = session.execute(text("SELECT count(*) FROM edge_country_flow WHERE release_id=:r"), {"r": geo_release_id}).scalar()
    return int(hubs), int(flows)
