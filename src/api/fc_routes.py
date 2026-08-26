"""Endpoint phục vụ các màn hình "Thành phố tài chính".

Mọi truy vấn ở đây đọc schema `fc` — bằng chứng quan sát được. Không endpoint
nào chạm vào `fc_gt`: đó là ground truth ẩn, chỉ dùng khi chấm điểm ngoại
tuyến. Nếu một màn hình cần con số từ `fc_gt` để hiển thị thì màn hình đó đang
tiết lộ đáp án cho chính người đang được đánh giá.

Hiện chưa có ngoại lệ nào. Chỉ số `detection_lead_time_days` — hiệu số giữa
thời điểm hành vi bắt đầu và tín hiệu quan sát được đầu tiên — được tính sẵn
ngoại tuyến rồi ghi vào `fc.benchmark_result`, nên endpoint benchmark cũng chỉ
đọc schema `fc`. Nếu sau này cần một endpoint tính trực tiếp từ `fc_gt`, nó
phải trả về khoảng thời gian đã tính sẵn chứ không phải các mốc thời gian gốc.
"""

import json
from collections.abc import Mapping
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, NamedTuple

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.bitcoin_aml.risk_reasons import build_risk_reasons
from src.db.session import get_session
from src.investigation.graph_narrative import narrate, read_neighbourhood
from src.models.fc_schemas import (
    AgentRunDetailOut,
    AgentRunListOut,
    AgentRunOut,
    AgentStepOut,
    BenchmarkOut,
    BitcoinDriverOut,
    BitcoinNeighbourOut,
    BitcoinPageOut,
    BitcoinScoredRowOut,
    BitcoinSummaryOut,
    CryptoOut,
    CryptoTransferOut,
    DataQualityOut,
    DetectedPatternOut,
    EdgeModelReleaseOut,
    EvidenceReasonOut,
    ExposureOut,
    RiskReasonOut,
    RiskReasonReference,
    FlowOut,
    GraphEdgeOut,
    GraphNarrativeOut,
    GraphNodeOut,
    GraphOut,
    HubOut,
    ModelBranchOut,
    ModelMonitorOut,
    NavCountsOut,
    ObservationOut,
    OperatingPointOut,
    PatternHopOut,
    ProjectOut,
    SearchHitOut,
    SourceOut,
    TxPageOut,
    TxRowOut,
    WorldOut,
)

router = APIRouter()


def _as_int(value: Any) -> int | None:
    """Ép về int khi có thể, None khi không — dùng cho các trường tuỳ chọn."""
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _f(value: Any) -> float:
    """NUMERIC của PostgreSQL về dưới dạng Decimal; JSON không có kiểu đó."""
    return float(value) if value is not None else 0.0


def _current_simulation(session) -> dict[str, Any] | None:
    row = (
        session.execute(
            text(
                """SELECT simulation_id, scenario_package
                     FROM fc.simulation_run
                    ORDER BY created_at DESC
                    LIMIT 1"""
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


# ---------------------------------------------------------------------
# Shell
# ---------------------------------------------------------------------


@router.get("/nav-counts", response_model=NavCountsOut)
def nav_counts() -> NavCountsOut:
    """Số việc tồn đọng hiển thị trên badge sidebar."""
    with get_session() as session:
        row = (
            session.execute(
                text(
                    # Đếm trên toàn bộ hàng đợi. Điều kiện cũ khoá theo edge-model
                    # release, mà nhánh rule và nhánh anomaly chấm điểm ở cấp tài khoản
                    # nên `alert.transaction_id` là NULL — badge hiện 0 trong khi hàng
                    # đợi có hai vạn cảnh báo.
                    """SELECT
                         (SELECT count(*) FROM alert WHERE status <> 'closed')        AS alerts,
                         (SELECT count(*) FROM approval ap
                           JOIN sar_draft sd USING (sar_draft_id)
                           WHERE ap.decision = 'pending')                             AS approvals,
                         (SELECT count(*) FROM alert
                           WHERE status <> 'closed' AND risk_score >= 80)             AS critical,
                         -- min/max đi qua transaction_time_idx nên gần như tức thì,
                         -- không phải quét 6,1 triệu dòng.
                         (SELECT min(occurred_at)::date FROM transaction)             AS data_period_start,
                         (SELECT max(occurred_at)::date FROM transaction)             AS data_period_end"""
                )
            )
            .mappings()
            .one()
        )
    return NavCountsOut(**dict(row))


@router.get("/search", response_model=list[SearchHitOut])
def search(q: str = Query(min_length=2, max_length=64)) -> list[SearchHitOut]:
    """Tra cứu nhanh cho bảng lệnh ⌘K.

    Chỉ khớp tiền tố hoặc chứa chuỗi, giới hạn 5 kết quả mỗi loại — bảng lệnh
    cần trả lời tức thì, không cần đầy đủ.
    """
    like = f"%{q.lower()}%"
    hits: list[SearchHitOut] = []
    with get_session() as session:
        for row in session.execute(
            text(
                """SELECT alert_id, typology_code FROM alert
                    WHERE lower(alert_id) LIKE :like
                      AND EXISTS (
                          SELECT 1 FROM transaction_model_score s
                          JOIN edge_model_release r USING (release_id)
                           WHERE r.status='active' AND s.transaction_id=alert.transaction_id
                      )
                    ORDER BY risk_score DESC LIMIT 5"""
            ),
            {"like": like},
        ).mappings():
            hits.append(
                SearchHitOut(
                    id=row["alert_id"],
                    label=row["alert_id"],
                    kind="Cảnh báo",
                    href=f"/alerts/{row['alert_id']}",
                )
            )

        for row in session.execute(
            text(
                """SELECT case_id, title FROM aml_case
                    WHERE (lower(case_id) LIKE :like OR lower(title) LIKE :like)
                      AND EXISTS (SELECT 1 FROM alert al WHERE al.case_id = aml_case.case_id)
                    ORDER BY risk_score DESC LIMIT 5"""
            ),
            {"like": like},
        ).mappings():
            hits.append(
                SearchHitOut(
                    id=row["case_id"],
                    label=f"{row['case_id']} · {row['title']}",
                    kind="Vụ việc",
                    href=f"/cases/{row['case_id']}",
                )
            )

    return hits


# ---------------------------------------------------------------------
# World Monitor
# ---------------------------------------------------------------------


class _Geography(NamedTuple):
    hubs: list[HubOut]
    flows: list[FlowOut]
    limitation: str | None


_MAX_FLOWS = 300


def _operational_geography(session: Any) -> _Geography:
    """Hub và hành lang dòng tiền dựng từ dữ liệu vận hành thật.

    Trả về bản đồ rỗng nếu chưa chạy `scripts/load_bank_geography.py` — không
    dựng bản đồ nửa vời từ dữ liệu chưa nạp.
    """
    # Bản rollup địa lý KHÔNG tra theo release đang hoạt động.
    #
    # Bộ IBM AML không mang quốc gia — nó phải suy từ tên ngân hàng, và bước ấy
    # chưa chạy được, nên trang này trống suốt. SAML-D thì có sẵn vị trí ngân
    # hàng trên từng giao dịch, và bản rollup dựng từ đó mang một release riêng
    # trạng thái 'reference': nó cung cấp bản đồ chứ không chấm điểm cạnh, nên
    # không được chiếm chỗ release đang phục vụ ba trang khác.
    release_id = session.execute(
        text(
            """SELECT release_id FROM edge_model_release
                WHERE status = 'reference'
                  AND release_id IN (SELECT release_id FROM edge_country_hub)
                ORDER BY trained_at DESC LIMIT 1"""
        )
    ).scalar_one_or_none()
    if release_id is None:
        return _Geography(
            hubs=[],
            flows=[],
            limitation=(
                "Chưa dựng bản đồ hành lang. Chạy scripts/build_geo_rollup.py sau khi "
                "đã nạp một bộ dữ liệu có quốc gia."
            ),
        )

    release_source = (
        session.execute(
            text("SELECT dataset FROM edge_model_release WHERE release_id = :r"),
            {"r": release_id},
        ).scalar_one_or_none()
        or "nguồn chưa rõ"
    )

    hub_rows = (
        session.execute(
            text(
                """SELECT g.country_code, g.name, g.lat, g.lon,
                          r.entities, r.inbound, r.outbound,
                          r.alerts, r.risk_score
                     FROM edge_country_hub r
                     JOIN country_geo g USING (country_code)
                    WHERE r.release_id=:release
                    ORDER BY r.inbound+r.outbound DESC"""
            ),
            {"release": release_id},
        )
        .mappings()
        .all()
    )
    if not hub_rows:
        return _Geography(
            hubs=[],
            flows=[],
            limitation="Chưa dựng geography rollup; chạy lại scripts/build_geo_rollup.py.",
        )

    flow_rows = (
        session.execute(
            text(
                """SELECT source_country_code AS src, target_country_code AS dst,
                          currency, channel, txn_count, amount_native,
                          first_seen, last_seen, alert_count, risk_score, typology_code
                     FROM edge_country_flow
                    WHERE release_id=:release
                    ORDER BY alert_count DESC, txn_count DESC
                    LIMIT :limit"""
            ),
            {"release": release_id, "limit": _MAX_FLOWS},
        )
        .mappings()
        .all()
    )

    # Độ phủ quốc gia phải đo trên CHÍNH bộ dữ liệu dựng nên bản đồ.
    #
    # Truy vấn cũ đếm trên toàn bộ `account` rồi nối sang `bank` — với dữ liệu
    # SAML-D thì phép nối ấy không khớp gì và trang báo "0,0% tài khoản có quốc
    # gia" ngay bên cạnh một bản đồ 18 quốc gia đầy dữ liệu. Số liệu tự mâu
    # thuẫn còn tệ hơn không có số liệu.
    # Độ phủ quốc gia là thuộc tính TĨNH của bộ dữ liệu (chỉ để hiển thị một câu
    # bên dưới). Đếm 9,5M dòng mỗi lần mở /world khiến trang treo ~11s. Đọc số đã
    # tính sẵn trong metadata release; chỉ đếm live khi metadata chưa có.
    meta = session.execute(
        text("SELECT benchmark FROM edge_model_release WHERE release_id = :r"),
        {"r": release_id},
    ).scalar_one_or_none()
    meta = meta if isinstance(meta, dict) else {}
    if meta.get("coverage_total") is not None:
        coverage = {"total": meta["coverage_total"], "located": meta.get("coverage_located", 0)}
    else:
        coverage = dict(
            session.execute(
                text(
                    """SELECT count(*) AS total,
                              count(*) FILTER (WHERE t.from_country IS NOT NULL) AS located
                         FROM transaction t
                        WHERE t.source_dataset = :source"""
                ),
                {"source": release_source},
            )
            .mappings()
            .one()
        )

    names = {row["country_code"]: row["name"] for row in hub_rows}
    coords = {row["country_code"]: (float(row["lat"]), float(row["lon"])) for row in hub_rows}

    hubs = [
        HubOut(
            id=row["country_code"],
            name=row["name"],
            country=row["country_code"],
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            # Chủ ý để "unknown": gán quốc gia là mô tả dữ liệu, còn gán mức rủi
            # ro pháp vực là phán đoán chính sách và phải có ngày hiệu lực.
            jurisdiction_risk="unknown",
            inbound=int(row["inbound"]),
            outbound=int(row["outbound"]),
            volume_usd=0,
            alerts=int(row["alerts"]),
            entities=int(row["entities"]),
            risk_score=int(row["risk_score"]),
        )
        for row in hub_rows
    ]

    flows = [
        FlowOut(
            id=f"{row['src']}-{row['dst']}-{row['currency']}",
            source_hub=row["src"],
            target_hub=row["dst"],
            source_name=names.get(row["src"], row["src"]),
            target_name=names.get(row["dst"], row["dst"]),
            slat=coords[row["src"]][0],
            slon=coords[row["src"]][1],
            tlat=coords[row["dst"]][0],
            tlon=coords[row["dst"]][1],
            channel=row["channel"],
            currency=row["currency"],
            amount_native=float(row["amount_native"]),
            volume_usd=0,
            txn_count=int(row["txn_count"]),
            risk_score=int(row["risk_score"]),
            typology_hint=row["typology_code"],
            alert_count=int(row["alert_count"]),
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
        )
        for row in flow_rows
        if row["src"] in coords and row["dst"] in coords
    ]

    total = int(coverage["total"]) or 1
    located = int(coverage["located"])
    limitation = (
        f"Bản đồ dựng từ {release_source}: {located:,}/{total:,} giao dịch có quốc gia "
        f"đọc thẳng từ dữ liệu gốc ({located / total:.1%}), không suy từ tên ngân hàng. "
        "Chỉ vẽ hành lang giữa hai quốc gia khác nhau; luồng nội địa không lên bản đồ. "
        "Chưa gán mức rủi ro pháp vực."
    )
    return _Geography(hubs=hubs, flows=flows, limitation=limitation)


@router.get("/world", response_model=WorldOut)
def world() -> WorldOut:
    """Bản đồ hành lang dòng tiền, dựng từ bộ dữ liệu có sẵn quốc gia.

    Nhãn nguồn phải lấy từ CHÍNH release dựng nên bản đồ. Lấy từ release đang
    hoạt động thì trang ghi "Dữ liệu IBM AML HI-Medium" ngay trên một bản đồ vẽ
    bằng SAML-D — sai nguồn là lỗi nặng hơn thiếu nhãn.
    """
    with get_session() as session:
        batch = (
            session.execute(
                text(
                    """SELECT release_id AS batch_id, dataset AS source_name,
                              transaction_rows AS transaction_count
                         FROM edge_model_release
                        WHERE status = 'reference'
                          AND release_id IN (SELECT release_id FROM edge_country_hub)
                        ORDER BY trained_at DESC LIMIT 1"""
                )
            )
            .mappings()
            .first()
        )
        geography = _operational_geography(session)
    return WorldOut(
        hubs=geography.hubs,
        flows=geography.flows,
        simulation_id=None,
        scenario_package=None,
        data_mode="operational",
        source_id=batch["batch_id"] if batch else None,
        source_name=batch["source_name"] if batch else None,
        transaction_count=int(batch["transaction_count"]) if batch else 0,
        geography_available=bool(geography.hubs),
        limitation=(geography.limitation if batch else "Chưa dựng bản đồ hành lang; chạy scripts/build_geo_rollup.py."),
    )


# ---------------------------------------------------------------------
# Đồ thị mạng lưới
# ---------------------------------------------------------------------

# Cạnh chưa có giao dịch nào đứng sau. Là giá trị hợp lệ, không phải lỗi: quan
# hệ sở hữu, dùng chung thiết bị hay chuyển on-chain vốn không sinh ra chuyển
# khoản ngân hàng nào.
_EMPTY_TX_METRICS: dict[str, Any] = {
    "tx_count": 0,
    "amounts_by_currency": {},
    "tx_first_seen": None,
    "tx_last_seen": None,
}

# Nối thực thể trong đồ thị với tài khoản trong sổ cái. `fc.entity` loại
# `account` lưu `account_key` trong attributes; bộ sinh ABM ghi khoá này bằng
# một hàm băm tất định để lần chạy sau vẫn nối lại được.
_ENTITY_ACCOUNT_JOIN = """
    fc.entity src
      ON src.simulation_id = :sid
     AND src.attributes ->> 'account_key' = t.from_account_key
    JOIN fc.entity dst
      ON dst.simulation_id = :sid
     AND dst.attributes ->> 'account_key' = t.to_account_key
"""


def _edge_transaction_metrics(session: Session, sim_id: str) -> dict[tuple[str, str], dict[str, Any]]:
    """Tổng hợp giao dịch thật thành số đo của từng cạnh quan hệ.

    Đây là chiều dữ liệu mà màn đồ thị vốn thiếu: cạnh nói *có quan hệ*, còn số
    ở đây nói *quan hệ đó dựa trên bao nhiêu sự kiện nào*. Gộp ở tầng SQL chứ
    không kéo giao dịch lên rồi gộp bằng Python — một cặp tài khoản có thể có
    hàng nghìn dòng, và đồ thị chỉ cần bốn con số.

    Tiền tệ KHÔNG được cộng gộp: `SUM(amount)` nhóm theo `currency` rồi mới xếp
    thành từ điển. Cộng 120.000 USD với 45.000 EUR thành 165.000 là sai về
    nghiệp vụ và analyst sẽ không phát hiện ra khi nhìn một con số duy nhất.
    """
    rows = (
        session.execute(
            text(
                f"""SELECT src.entity_id AS source_id,
                           dst.entity_id AS target_id,
                           t.currency,
                           count(*)      AS n,
                           sum(t.amount) AS total,
                           min(t.occurred_at) AS first_seen,
                           max(t.occurred_at) AS last_seen
                      FROM transaction t
                      JOIN {_ENTITY_ACCOUNT_JOIN}
                     GROUP BY src.entity_id, dst.entity_id, t.currency"""  # noqa: S608 — join là hằng số
            ),
            {"sid": sim_id},
        )
        .mappings()
        .all()
    )

    out: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r["source_id"], r["target_id"])
        bucket = out.setdefault(
            key,
            {"tx_count": 0, "amounts_by_currency": {}, "tx_first_seen": None, "tx_last_seen": None},
        )
        bucket["tx_count"] += r["n"]
        bucket["amounts_by_currency"][r["currency"]] = _f(r["total"])
        first, last = r["first_seen"], r["last_seen"]
        if bucket["tx_first_seen"] is None or first < bucket["tx_first_seen"]:
            bucket["tx_first_seen"] = first
        if bucket["tx_last_seen"] is None or last > bucket["tx_last_seen"]:
            bucket["tx_last_seen"] = last
    return out


#: Lấy lân cận giao dịch của các tài khoản hạt giống.
#:
#: Bản trước viết ``WHERE from_account_key = ANY(seeds) OR to_account_key =
#: ANY(seeds)`` rồi nối thẳng với bảng 6,1 triệu điểm và sắp xếp toàn bộ kết quả.
#: Dấu OR khiến PostgreSQL không dùng được cả hai chỉ mục theo tài khoản, còn
#: ORDER BY trên cột của bảng điểm buộc nó phải vật chất hoá mọi dòng khớp
#: trước khi cắt LIMIT. Trên Cloud SQL, câu ấy mất **302 giây**.
#:
#: Bản này đổi cách chọn: mỗi tài khoản hạt giống lấy N giao dịch gần nhất qua
#: đúng hai chỉ mục ``(account, occurred_at DESC)`` đã có, rồi mới tra điểm theo
#: khoá chính. Ý nghĩa hiển thị cũng đổi theo — "giao dịch gần nhất của từng tài
#: khoản rủi ro cao" thay vì "giao dịch điểm cao nhất toàn hệ thống" — và đó là
#: lựa chọn có chủ đích: một đồ thị lân cận phải phủ đều các đỉnh gốc, chứ không
#: dồn hết cạnh vào một hai tài khoản sôi động nhất.
_NEIGHBOURHOOD_SQL = """
    WITH seed AS (
        SELECT unnest(CAST(:seeds AS text[])) AS account_key
    ),
    active AS (
        SELECT release_id FROM edge_model_release WHERE status = 'active' LIMIT 1
    ),
    neighbourhood AS (
        SELECT e.*
          FROM seed
          CROSS JOIN LATERAL (
              (SELECT t.transaction_id, t.occurred_at, t.from_account_key,
                      t.to_account_key, t.amount, t.currency, t.channel
                 FROM transaction t
                WHERE t.from_account_key = seed.account_key
                ORDER BY t.occurred_at DESC
                LIMIT :per_seed)
              UNION ALL
              (SELECT t.transaction_id, t.occurred_at, t.from_account_key,
                      t.to_account_key, t.amount, t.currency, t.channel
                 FROM transaction t
                WHERE t.to_account_key = seed.account_key
                ORDER BY t.occurred_at DESC
                LIMIT :per_seed)
          ) e
    ),
    deduped AS (
        -- Một giao dịch giữa hai tài khoản hạt giống xuất hiện hai lần; giữ một.
        SELECT DISTINCT ON (transaction_id) *
          FROM neighbourhood
         ORDER BY transaction_id
    )
    SELECT d.transaction_id, d.occurred_at, d.from_account_key, d.to_account_key,
           d.amount, d.currency, d.channel, s.model_score
      FROM deduped d
      CROSS JOIN active a
      LEFT JOIN transaction_model_score s
             ON s.transaction_id = d.transaction_id
            AND s.release_id = a.release_id
     ORDER BY s.triggered DESC NULLS LAST, s.model_score DESC NULLS LAST, d.occurred_at DESC
     LIMIT :lim
"""


def _operational_transaction_graph(
    session: Session, limit: int, dataset: str | None = None, seed_account: str | None = None
) -> GraphOut:
    """Đồ thị quanh các cảnh báo rủi ro cao, dựng từ giao dịch đã chấm điểm.

    Hạt giống lấy **trực tiếp từ bảng alert**, không nối qua
    ``transaction_model_score``. Ba nhánh phát hiện (rule, anomaly, graph) đều
    chấm ở cấp **tài khoản** nên ``alert.transaction_id`` là NULL cho toàn bộ
    21.034 cảnh báo; phép nối cũ không khớp dòng nào và đồ thị luôn rỗng.

    Điểm của mô hình cạnh vẫn được dùng — nhưng ở bước sau, để tô màu rủi ro cho
    từng cạnh giao dịch, chứ không phải để chọn hạt giống.
    """
    # Ưu tiên tài khoản CÓ mẫu hình do bộ dò đồ thị ghi nhận.
    #
    # Trước đây chỉ xếp theo `max(risk_score) DESC, account_key`. Nhưng 9.084
    # cảnh báo đang mở cùng đạt điểm 100,0, nên thứ tự thực chất là **bảng chữ
    # cái** — và 25 tài khoản đầu bảng đều là cảnh báo luật, không tài khoản nào
    # có cấu trúc đồ thị. Đo được: 0 trên 25 hạt giống có bằng chứng bộ dò, trong
    # khi 332 tài khoản khác vừa có cảnh báo mở vừa có mẫu hình.
    #
    # Hệ quả là đồ thị vẽ ra một hình sao không mang thông tin gì, tab Chu trình
    # luôn rỗng, và chuyên viên không có gì để đọc. Xếp tài khoản có mẫu hình lên
    # trước để vùng vẽ chứa đúng thứ đáng nhìn.
    if seed_account:
        # Đồ thị GẮN THEO MỘT VỤ: gieo mầm đúng bằng tài khoản chủ thể của vụ,
        # rồi nở ra vùng lân cận của nó. Nhờ vậy giao diện đồ thị giàu (Cytoscape)
        # vẽ đúng mạng lưới quanh vụ đang xem, thay vì toàn bộ release.
        risk = (
            session.execute(
                text("SELECT max(risk_score) FROM alert WHERE account_key = :a"),
                {"a": seed_account},
            ).scalar()
        )
        seeds = [seed_account]
        seed_risk = {seed_account: int(round(_f(risk))) if risk is not None else 80}
    else:
        seed_limit = max(10, min(100, limit // 4))
        seed_rows = (
            session.execute(
                text(
                    """SELECT a.account_key,
                              max(a.risk_score) AS risk_score,
                              bool_or(g.account_key IS NOT NULL) AS has_pattern
                         FROM alert a
                         LEFT JOIN graph_detector_evidence g ON g.account_key = a.account_key
                        WHERE a.status <> 'closed'
                          -- Gieo mầm theo đúng bộ dữ liệu đang xem: cả đồ thị nở ra
                          -- từ hạt giống nên lọc ở đây là scope toàn bộ. Không lọc thì
                          -- một cụm tài khoản IBM và một cụm SAML-D nằm chung khung vẽ,
                          -- vốn là hai vũ trụ không có cạnh nào nối nhau.
                          AND (CAST(:dataset AS text) IS NULL OR a.dataset = CAST(:dataset AS text))
                        GROUP BY a.account_key
                        ORDER BY has_pattern DESC, max(a.risk_score) DESC, a.account_key
                        LIMIT :lim"""
                ),
                {"lim": seed_limit, "dataset": dataset},
            )
            .mappings()
            .all()
        )
        if not seed_rows:
            return GraphOut(nodes=[], edges=[])
        seeds = [row["account_key"] for row in seed_rows]
        seed_risk = {row["account_key"]: int(round(_f(row["risk_score"]))) for row in seed_rows}
    # Lấy gấp đôi số đỉnh cần vẽ, không gấp tám như trước. Mỗi cạnh mang tối đa
    # hai đỉnh nên chừng ấy dòng đã thừa để chạm trần `limit`, và phần dư bị vòng
    # lặp bên dưới bỏ đi. Trên Cloud SQL, mỗi dòng thừa là một lần đọc khối ngẫu
    # nhiên mất vài mili giây — hạ 8× xuống 2× rút thời gian lần gọi nguội từ
    # khoảng 100 giây xuống khoảng 30, và lần gọi ấm xuống dưới 2 giây.
    fetch = limit * 2
    rows = (
        session.execute(
            text(_NEIGHBOURHOOD_SQL),
            {"seeds": seeds, "per_seed": max(4, fetch // len(seeds)), "lim": fetch},
        )
        .mappings()
        .all()
    )

    node_data: dict[str, dict[str, Any]] = {}
    edge_data: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        source = row["from_account_key"]
        target = row["to_account_key"]
        new_nodes = {source, target} - node_data.keys()
        if len(node_data) + len(new_nodes) > limit:
            continue
        when = row["occurred_at"]
        risk = int(round(_f(row["model_score"]) * 100))
        for account_key in (source, target):
            current = node_data.get(account_key)
            if current is None:
                node_data[account_key] = {"first": when, "last": when, "risk": seed_risk.get(account_key, risk)}
            else:
                current["first"] = min(current["first"], when)
                current["last"] = max(current["last"], when)
                current["risk"] = max(current["risk"], seed_risk.get(account_key, risk))
        edge = edge_data.setdefault(
            (source, target),
            {
                "count": 0,
                "amounts": {},
                "first": when,
                "last": when,
                "risk": risk,
            },
        )
        edge["count"] += 1
        edge["amounts"][row["currency"]] = edge["amounts"].get(row["currency"], 0.0) + _f(row["amount"])
        edge["first"] = min(edge["first"], when)
        edge["last"] = max(edge["last"], when)
        edge["risk"] = max(edge["risk"], risk)

    return GraphOut(
        nodes=[
            GraphNodeOut(
                id=account_key,
                type="account",
                label=account_key,
                sub=("Tài khoản có cảnh báo model" if account_key in seed_risk else "Tài khoản đối tác giao dịch"),
                risk=values["risk"],
                first=values["first"],
                last=values["last"],
                hub=account_key.split(":", 1)[0],
                negative=False,
            )
            for account_key, values in node_data.items()
        ],
        edges=[
            GraphEdgeOut(
                id=f"TX|{source}|{target}",
                s=source,
                t=target,
                kind="transfer",
                label=f"{values['count']:,} giao dịch · rủi ro {values['risk']}",
                amt=None,
                inferred=False,
                conf=1.0,
                logic="Cạnh quan sát trực tiếp từ sổ giao dịch HI-Medium; số tiền được giữ riêng theo currency.",
                known_from=values["first"],
                tx_count=values["count"],
                amounts_by_currency=values["amounts"],
                tx_first_seen=values["first"],
                tx_last_seen=values["last"],
            )
            for (source, target), values in edge_data.items()
        ],
    )


@router.get("/fc/graph", response_model=GraphOut)
def entity_graph(
    limit: int = Query(default=400, le=2000),
    dataset: str | None = Query(default=None, description="ibm_hi_medium | saml_d"),
    subject: str | None = Query(
        default=None,
        description="Tài khoản chủ thể của một vụ việc — trả đồ thị vận hành GẮN THEO VỤ (seed từ tài khoản này).",
    ),
) -> GraphOut:
    """Toàn bộ đồ thị thực thể của lần chạy mô phỏng gần nhất.

    ``dataset`` chỉ áp cho đồ thị vận hành (dựng từ cảnh báo thật). Lần chạy mô
    phỏng là một vũ trụ thực thể riêng, không gắn bộ dữ liệu vận hành nào.

    ``subject`` (tài khoản chủ thể của một vụ) buộc dùng đồ thị VẬN HÀNH gieo mầm
    từ tài khoản đó — dùng cho tab Đồ thị trong trang vụ việc.
    """
    with get_session() as session:
        if subject:
            return _operational_transaction_graph(session, limit, dataset, seed_account=subject)
        sim = _current_simulation(session)
        if not sim:
            return _operational_transaction_graph(session, limit, dataset)

        nodes = (
            session.execute(
                text(
                    """SELECT entity_id, entity_type, label, subtitle, risk_score,
                              first_seen, last_seen, hub_id, is_hard_negative
                         FROM fc.entity
                        WHERE simulation_id = :sid
                        ORDER BY risk_score DESC
                        LIMIT :lim"""
                ),
                {"sid": sim["simulation_id"], "lim": limit},
            )
            .mappings()
            .all()
        )
        ids = {n["entity_id"] for n in nodes}

        edges = (
            session.execute(
                text(
                    """SELECT relationship_id, source_id, target_id, kind, label, amount_usd,
                              is_inferred, confidence, inference_logic, known_from
                         FROM fc.relationship
                        WHERE simulation_id = :sid"""
                ),
                {"sid": sim["simulation_id"]},
            )
            .mappings()
            .all()
        )

        # Chặng crypto nằm ở bảng riêng vì nó đến từ dữ liệu on-chain, không
        # phải từ hệ thống ngân hàng. Không gộp vào đây thì mọi ví trong đồ thị
        # đứng rời rạc và toàn bộ đoạn cuối của dòng tiền biến mất.
        #
        # Nối bằng `attributes->>'address'`: `fc.entity` lưu địa chỉ đầy đủ
        # trong attributes, còn `label` chỉ là bản rút gọn để hiển thị.
        crypto = (
            session.execute(
                text(
                    """SELECT src.entity_id AS source_id,
                              dst.entity_id AS target_id,
                              ct.transfer_kind,
                              ct.chain,
                              ct.asset,
                              SUM(ct.amount_usd) AS amount_usd,
                              AVG(ct.link_confidence) AS confidence,
                              COUNT(*) AS n_tx,
                              MIN(ct.block_time) AS known_from
                         FROM fc.crypto_transfer ct
                         JOIN fc.entity src
                           ON src.attributes ->> 'address' = ct.from_address
                          AND src.simulation_id = ct.simulation_id
                         JOIN fc.entity dst
                           ON dst.attributes ->> 'address' = ct.to_address
                          AND dst.simulation_id = ct.simulation_id
                        WHERE ct.simulation_id = :sid
                        GROUP BY src.entity_id, dst.entity_id, ct.transfer_kind,
                                 ct.chain, ct.asset"""
                ),
                {"sid": sim["simulation_id"]},
            )
            .mappings()
            .all()
        )

        tx_metrics = _edge_transaction_metrics(session, sim["simulation_id"])

    crypto_edges = [
        GraphEdgeOut(
            id=f"CRY-{c['source_id']}-{c['target_id']}-{c['transfer_kind']}-{c['asset']}",
            s=c["source_id"],
            t=c["target_id"],
            kind="bridge" if c["transfer_kind"] == "bridge" else "crypto",
            label=f"{c['n_tx']} giao dịch {c['asset']}",
            amt=_f(c["amount_usd"]) if c["amount_usd"] is not None else None,
            # Gán ví với chủ thể ngoài đời là suy luận, không phải quan sát —
            # `link_confidence` chính là mức tin cậy của phép gán đó.
            inferred=c["confidence"] is not None,
            conf=_f(c["confidence"]) if c["confidence"] is not None else None,
            logic=(
                f"Gộp {c['n_tx']} giao dịch {c['asset']} trên {c['chain']} giữa hai địa chỉ ví. "
                "Việc quy địa chỉ về chủ thể dựa trên phân cụm heuristic, chưa có xác nhận từ VASP."
            )
            if c["confidence"] is not None
            else None,
            known_from=c["known_from"],
        )
        for c in crypto
        if c["source_id"] in ids and c["target_id"] in ids
    ]

    return GraphOut(
        nodes=[
            GraphNodeOut(
                id=n["entity_id"],
                type=n["entity_type"],
                label=n["label"],
                sub=n["subtitle"],
                risk=n["risk_score"],
                first=n["first_seen"],
                last=n["last_seen"],
                hub=n["hub_id"],
                negative=n["is_hard_negative"],
            )
            for n in nodes
        ],
        # Bỏ cạnh trỏ tới đỉnh đã bị `limit` cắt — đồ thị có cạnh treo sẽ làm
        # engine layout văng.
        edges=[
            GraphEdgeOut(
                id=e["relationship_id"],
                s=e["source_id"],
                t=e["target_id"],
                kind=e["kind"],
                label=e["label"],
                amt=_f(e["amount_usd"]) if e["amount_usd"] is not None else None,
                inferred=e["is_inferred"],
                conf=_f(e["confidence"]) if e["confidence"] is not None else None,
                logic=e["inference_logic"],
                known_from=e["known_from"],
                **tx_metrics.get((e["source_id"], e["target_id"]), _EMPTY_TX_METRICS),
            )
            for e in edges
            if e["source_id"] in ids and e["target_id"] in ids
        ]
        + crypto_edges,
    )


@router.get("/fc/graph/edges/{edge_id}/transactions", response_model=TxPageOut)
def edge_transactions(
    edge_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    min_amount: float = Query(default=0, ge=0),
    currency: str = Query(default="all", max_length=64),
) -> TxPageOut:
    """Những giao dịch thật nằm sau một cạnh quan hệ.

    Đây là bước xuống tầng của màn điều tra: đồ thị vẽ *quan hệ*, còn đây là
    *sự kiện* làm nên quan hệ đó. Tách ra thành lời gọi riêng chứ không nhét
    vào `/fc/graph` — một cặp tài khoản có thể có hàng nghìn giao dịch, và
    nhét chúng vào phản hồi đồ thị sẽ biến một màn hình 60 cạnh thành vài MB
    JSON mà 99% không bao giờ được mở ra xem.

    Trả về danh sách rỗng khi cạnh không có giao dịch nào đứng sau — quan hệ sở
    hữu, dùng chung thiết bị hay chuyển on-chain đều rơi vào trường hợp này.
    Giao diện có nhiệm vụ nói thẳng điều đó thay vì dựng ra một con số.
    """
    with get_session() as session:
        sim = _current_simulation(session)
        if not sim:
            parts = edge_id.split("|", 2)
            if len(parts) != 3 or parts[0] != "TX":
                raise HTTPException(status_code=404, detail=f"Không có cạnh giao dịch {edge_id}.")
            source, target = parts[1], parts[2]
            where = ["t.from_account_key=:source", "t.to_account_key=:target", "r.status='active'"]
            params: dict[str, Any] = {
                "source": source,
                "target": target,
                "limit": page_size,
                "offset": (page - 1) * page_size,
            }
            if min_amount > 0:
                where.append("t.amount >= :min_amount")
                params["min_amount"] = min_amount
            if currency != "all":
                where.append("t.currency = :currency")
                params["currency"] = currency
            clause = " AND ".join(where)
            total = session.execute(
                text(
                    f"""SELECT count(*) FROM transaction t
                          JOIN transaction_model_score s USING (transaction_id)
                          JOIN edge_model_release r USING (release_id)
                         WHERE {clause}"""  # noqa: S608
                ),
                params,
            ).scalar_one()
            rows = (
                session.execute(
                    text(
                        f"""SELECT t.transaction_id, t.source_transaction_id, t.occurred_at,
                                   t.from_account_key, t.to_account_key, t.amount, t.currency,
                                   t.amount_received, t.receiving_currency, t.channel, t.remarks,
                                   s.model_score, s.threshold, s.triggered, r.model_version
                              FROM transaction t
                              JOIN transaction_model_score s USING (transaction_id)
                              JOIN edge_model_release r USING (release_id)
                             WHERE {clause}
                             ORDER BY t.occurred_at DESC
                             LIMIT :limit OFFSET :offset"""  # noqa: S608
                    ),
                    params,
                )
                .mappings()
                .all()
            )
            return TxPageOut(
                rows=[
                    TxRowOut(
                        id=row["transaction_id"],
                        source_id=row["source_transaction_id"],
                        occurred_at=row["occurred_at"],
                        from_account=row["from_account_key"],
                        to_account=row["to_account_key"],
                        amount=_f(row["amount"]),
                        currency=row["currency"],
                        amount_received=_f(row["amount_received"]),
                        receiving_currency=row["receiving_currency"],
                        channel=row["channel"],
                        remarks=row["remarks"],
                        model_score=_f(row["model_score"]),
                        threshold=_f(row["threshold"]),
                        triggered=row["triggered"],
                        model_version=row["model_version"],
                    )
                    for row in rows
                ],
                total=total,
                page=page,
                page_size=page_size,
            )

        rel = (
            session.execute(
                text(
                    """SELECT source_id, target_id
                         FROM fc.relationship
                        WHERE relationship_id = :rid AND simulation_id = :sid"""
                ),
                {"rid": edge_id, "sid": sim["simulation_id"]},
            )
            .mappings()
            .first()
        )
        if not rel:
            raise HTTPException(status_code=404, detail=f"Không có quan hệ {edge_id}.")

        where = ["src.entity_id = :source", "dst.entity_id = :target"]
        params: dict[str, Any] = {
            "sid": sim["simulation_id"],
            "source": rel["source_id"],
            "target": rel["target_id"],
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        if min_amount > 0:
            where.append("t.amount >= :min_amount")
            params["min_amount"] = min_amount
        if currency != "all":
            where.append("t.currency = :currency")
            params["currency"] = currency
        clause = " AND ".join(where)

        total = session.execute(
            text(
                f"""SELECT count(*)
                      FROM transaction t
                      JOIN {_ENTITY_ACCOUNT_JOIN}
                     WHERE {clause}"""  # noqa: S608 — clause dựng từ hằng số
            ),
            params,
        ).scalar_one()

        rows = (
            session.execute(
                text(
                    f"""SELECT t.transaction_id, t.occurred_at, t.from_account_key, t.to_account_key,
                               t.amount, t.currency, t.channel, t.remarks
                          FROM transaction t
                          JOIN {_ENTITY_ACCOUNT_JOIN}
                         WHERE {clause}
                         ORDER BY t.occurred_at DESC
                         LIMIT :limit OFFSET :offset"""  # noqa: S608
                ),
                params,
            )
            .mappings()
            .all()
        )

    return TxPageOut(
        rows=[
            TxRowOut(
                id=r["transaction_id"],
                occurred_at=r["occurred_at"],
                from_account=r["from_account_key"],
                to_account=r["to_account_key"],
                amount=_f(r["amount"]),
                currency=r["currency"],
                channel=r["channel"],
                remarks=r["remarks"],
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/fc/graph/nodes/{node_id}/transactions", response_model=TxPageOut)
def node_transactions(
    node_id: str,
    direction: Literal["all", "in", "out"] = Query(default="all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> TxPageOut:
    """Giao dịch của một thực thể, cả hai chiều hoặc một chiều."""
    with get_session() as session:
        sim = _current_simulation(session)
        if not sim:
            key = session.execute(
                text("SELECT account_key FROM account WHERE account_key=:key"), {"key": node_id}
            ).scalar_one_or_none()
            if key is None:
                raise HTTPException(status_code=404, detail=f"Không có tài khoản {node_id}.")
            if direction == "in":
                clause = "t.to_account_key = :key"
            elif direction == "out":
                clause = "t.from_account_key = :key"
            else:
                clause = "(t.from_account_key = :key OR t.to_account_key = :key)"
            params = {"key": key, "limit": page_size, "offset": (page - 1) * page_size}
            total = session.execute(
                text(f"SELECT count(*) FROM transaction t WHERE {clause}"),
                params,  # noqa: S608
            ).scalar_one()
            rows = (
                session.execute(
                    text(
                        f"""SELECT t.transaction_id, t.source_transaction_id, t.occurred_at,
                                   t.from_account_key, t.to_account_key, t.amount, t.currency,
                                   t.amount_received, t.receiving_currency, t.channel, t.remarks,
                                   s.model_score, s.threshold, s.triggered, r.model_version
                              FROM transaction t
                              JOIN transaction_model_score s USING (transaction_id)
                              JOIN edge_model_release r USING (release_id)
                             WHERE r.status='active' AND {clause}
                             ORDER BY t.occurred_at DESC LIMIT :limit OFFSET :offset"""  # noqa: S608
                    ),
                    params,
                )
                .mappings()
                .all()
            )
            return TxPageOut(
                rows=[
                    TxRowOut(
                        id=row["transaction_id"],
                        source_id=row["source_transaction_id"],
                        occurred_at=row["occurred_at"],
                        from_account=row["from_account_key"],
                        to_account=row["to_account_key"],
                        amount=_f(row["amount"]),
                        currency=row["currency"],
                        amount_received=_f(row["amount_received"]),
                        receiving_currency=row["receiving_currency"],
                        channel=row["channel"],
                        remarks=row["remarks"],
                        model_score=_f(row["model_score"]),
                        threshold=_f(row["threshold"]),
                        triggered=row["triggered"],
                        model_version=row["model_version"],
                    )
                    for row in rows
                ],
                total=total,
                page=page,
                page_size=page_size,
            )

        key = session.execute(
            text(
                """SELECT attributes ->> 'account_key'
                     FROM fc.entity
                    WHERE entity_id = :eid AND simulation_id = :sid"""
            ),
            {"eid": node_id, "sid": sim["simulation_id"]},
        ).scalar_one_or_none()
        # Thực thể không phải tài khoản (người, thiết bị, ví) thì không có sổ
        # cái ngân hàng nào cả — trả rỗng chứ không phải lỗi.
        if not key:
            return TxPageOut(rows=[], total=0, page=page, page_size=page_size)

        if direction == "in":
            clause = "t.to_account_key = :key"
        elif direction == "out":
            clause = "t.from_account_key = :key"
        else:
            clause = "(t.from_account_key = :key OR t.to_account_key = :key)"
        params = {"key": key, "limit": page_size, "offset": (page - 1) * page_size}

        total = session.execute(
            text(f"SELECT count(*) FROM transaction t WHERE {clause}"),  # noqa: S608
            params,
        ).scalar_one()
        rows = (
            session.execute(
                text(
                    f"""SELECT t.transaction_id, t.occurred_at, t.from_account_key, t.to_account_key,
                               t.amount, t.currency, t.channel, t.remarks
                          FROM transaction t
                         WHERE {clause}
                         ORDER BY t.occurred_at DESC
                         LIMIT :limit OFFSET :offset"""  # noqa: S608
                ),
                params,
            )
            .mappings()
            .all()
        )

    return TxPageOut(
        rows=[
            TxRowOut(
                id=r["transaction_id"],
                occurred_at=r["occurred_at"],
                from_account=r["from_account_key"],
                to_account=r["to_account_key"],
                amount=_f(r["amount"]),
                currency=r["currency"],
                channel=r["channel"],
                remarks=r["remarks"],
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------
# Crypto và dự án token
# ---------------------------------------------------------------------


@router.get("/fc/crypto", response_model=CryptoOut)
def crypto(limit: int = Query(default=200, le=1000)) -> CryptoOut:
    with get_session() as session:
        sim = _current_simulation(session)
        if not sim:
            rows = (
                session.execute(
                    text(
                        # Chọn trước, chấm điểm sau. Sắp theo `s.model_score`
                        # ngay trong phép nối buộc PostgreSQL dựng toàn bộ
                        # 264 nghìn dòng khớp rồi mới cắt LIMIT; lấy N dòng gần
                        # nhất qua `transaction_crypto_idx` rồi mới tra điểm thì
                        # chỉ chạm đúng N dòng. Mệnh đề WHERE phải giữ nguyên
                        # văn để khớp điều kiện của chỉ mục một phần.
                        """WITH recent AS (
                               SELECT t.transaction_id, t.source_transaction_id, t.occurred_at,
                                      t.from_account_key, t.to_account_key, t.amount, t.currency
                                 FROM transaction t
                                WHERE t.currency='Bitcoin' OR t.receiving_currency='Bitcoin'
                                   OR t.channel='BITCOIN'
                                ORDER BY t.occurred_at DESC
                                LIMIT :lim
                           ),
                           active AS (
                               SELECT release_id FROM edge_model_release WHERE status='active' LIMIT 1
                           )
                           SELECT r.transaction_id, r.source_transaction_id, r.occurred_at,
                                  r.from_account_key, r.to_account_key, r.amount, r.currency
                             FROM recent r
                             CROSS JOIN active a
                             LEFT JOIN transaction_model_score s
                                    ON s.transaction_id = r.transaction_id
                                   AND s.release_id = a.release_id
                            ORDER BY s.model_score DESC NULLS LAST, r.occurred_at DESC"""
                    ),
                    {"lim": limit},
                )
                .mappings()
                .all()
            )
            return CryptoOut(
                transfers=[
                    CryptoTransferOut(
                        id=f"LEDGER-{row['transaction_id']}",
                        chain="IBM AML synthetic ledger",
                        tx_hash=row["source_transaction_id"] or str(row["transaction_id"]),
                        from_address=row["from_account_key"],
                        to_address=row["to_account_key"],
                        asset=row["currency"],
                        amount=_f(row["amount"]),
                        amount_usd=None,
                        block_time=row["occurred_at"],
                        kind="ledger",
                        link_confidence=None,
                    )
                    for row in rows
                ],
                exposures=[],
                total_usd=0,
                source_mode="ledger",
            )

        transfers = (
            session.execute(
                text(
                    """SELECT transfer_id, chain, tx_hash, from_address, to_address, asset,
                              amount, amount_usd, block_time, transfer_kind, link_confidence
                         FROM fc.crypto_transfer
                        WHERE simulation_id = :sid
                        ORDER BY block_time DESC
                        LIMIT :lim"""
                ),
                {"sid": sim["simulation_id"], "lim": limit},
            )
            .mappings()
            .all()
        )
        exposures = (
            session.execute(
                text(
                    """SELECT address, service_id, service_type, exposure_kind, hops,
                              confidence, source_id, known_from
                         FROM fc.exposure_label
                        ORDER BY confidence DESC
                        LIMIT :lim"""
                ),
                {"lim": limit},
            )
            .mappings()
            .all()
        )

    return CryptoOut(
        transfers=[
            CryptoTransferOut(
                id=t["transfer_id"],
                chain=t["chain"],
                tx_hash=t["tx_hash"],
                from_address=t["from_address"],
                to_address=t["to_address"],
                asset=t["asset"],
                amount=_f(t["amount"]),
                amount_usd=_f(t["amount_usd"]),
                block_time=t["block_time"],
                kind=t["transfer_kind"],
                link_confidence=_f(t["link_confidence"]) if t["link_confidence"] is not None else None,
            )
            for t in transfers
        ],
        exposures=[
            ExposureOut(
                address=e["address"],
                service_id=e["service_id"],
                service_type=e["service_type"],
                exposure_kind=e["exposure_kind"],
                hops=e["hops"],
                confidence=_f(e["confidence"]),
                source_id=e["source_id"],
                known_from=e["known_from"],
            )
            for e in exposures
        ],
        total_usd=sum(_f(t["amount_usd"]) for t in transfers),
    )


@lru_cache(maxsize=1)
def _bitcoin_distribution() -> dict[str, Any]:
    """Phân phối train của các đặc trưng (percentile) — nạp một lần cho risk_reasons.

    Thiếu file thì trả rỗng: risk_reasons vẫn dựng được (chỉ không có percentile).
    """
    path = Path("data/models/bitcoin_elliptic/feature_distribution.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — không có phân phối thì bỏ percentile
        return {}


@router.get("/fc/bitcoin", response_model=BitcoinPageOut)
def bitcoin_queue(
    view: str = Query(default="flagged", description="flagged | review | all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=10, le=200),
) -> BitcoinPageOut:
    """Hàng đợi giao dịch Bitcoin bị Random Forest chấm nghi ngờ (nhánh Elliptic gốc).

    Đọc thẳng bảng ``bitcoin_scored_tx`` — điểm tập test chấm sẵn bằng script,
    KHÔNG chấm lúc gọi. Đây là nhánh riêng, tách khỏi cảnh báo–tài khoản của
    IBM/SAML-D vì Elliptic ẩn danh (không địa chỉ ví, không tài khoản).

    ``view``: ``flagged`` (model gắn cờ bất hợp pháp — mặc định, đây là việc cần
    làm), ``review`` (chỉ mức HIGH/CRITICAL), ``all`` (toàn tập test).
    """
    # Bộ lọc hàng đợi. Tóm tắt LUÔN tính trên toàn tập, không theo bộ lọc.
    row_filter = {
        "flagged": "predicted_label = 'illicit'",
        "review": "requires_review",
        "all": "TRUE",
    }.get(view, "predicted_label = 'illicit'")

    with get_session() as session:
        # Chưa nạp điểm thì trả tóm tắt rỗng có nghĩa, không phải 500 — trang tự
        # hiện trạng thái "chưa nạp" kèm hướng dẫn chạy script.
        scored_total = session.execute(text("SELECT count(*) FROM bitcoin_scored_tx")).scalar_one()
        if not scored_total:
            empty = BitcoinSummaryOut(
                release_id="REL-BTC-ELLIPTICPP-V1",
                model_version="—",
                total_scored=0,
                flagged_illicit=0,
                requires_review=0,
                illicit_true_total=0,
                flagged_true_positive=0,
            )
            return BitcoinPageOut(summary=empty, rows=[], total=0, page=page, page_size=page_size)

        agg = (
            session.execute(
                text(
                    """SELECT
                         count(*)                                                   AS total_scored,
                         count(*) FILTER (WHERE predicted_label='illicit')          AS flagged_illicit,
                         count(*) FILTER (WHERE requires_review)                     AS requires_review,
                         count(*) FILTER (WHERE true_label='illicit')               AS illicit_true_total,
                         count(*) FILTER (WHERE predicted_label='illicit'
                                            AND true_label='illicit')               AS flagged_true_positive,
                         count(*) FILTER (WHERE risk_level='CRITICAL')              AS lvl_critical,
                         count(*) FILTER (WHERE risk_level='HIGH')                  AS lvl_high,
                         count(*) FILTER (WHERE risk_level='MEDIUM')                AS lvl_medium,
                         count(*) FILTER (WHERE risk_level='LOW')                   AS lvl_low,
                         min(timestep)                                              AS ts_min,
                         max(timestep)                                              AS ts_max,
                         max(release_id)                                            AS release_id
                       FROM bitcoin_scored_tx"""
                )
            )
            .mappings()
            .one()
        )
        # Chỉ số đầu bảng lấy từ release đã ký — cùng nguồn với trang Đánh giá
        # chuẩn, để hai chỗ không lệch số.
        rel = (
            session.execute(
                text(
                    """SELECT model_version, benchmark
                         FROM edge_model_release WHERE release_id = :rid"""
                ),
                {"rid": agg["release_id"]},
            )
            .mappings()
            .one_or_none()
        )
        primary = ((rel or {}).get("benchmark") or {}).get("primary_seed", {}) if rel else {}

        total = session.execute(
            text(f"SELECT count(*) FROM bitcoin_scored_tx WHERE {row_filter}")  # noqa: S608
        ).scalar_one()
        rows = (
            session.execute(
                text(
                    f"""SELECT tx_id, timestep, illicit_prob, predicted_label, true_label,
                               risk_level, requires_review, headline, reasons, caveat,
                               drivers, meaningful_push_share, interpretable_ratio,
                               explanation_quality, graph_in_degree, graph_out_degree,
                               graph_flagged_neighbours, graph_known_illicit_neighbours,
                               graph_neighbours, evidence_strength, graph_evidence,
                               evidence_reasons, recommended_steps
                          FROM bitcoin_scored_tx
                         WHERE {row_filter}
                         ORDER BY illicit_prob DESC, tx_id
                         LIMIT :limit OFFSET :offset"""  # noqa: S608
                ),
                {"limit": page_size, "offset": (page - 1) * page_size},
            )
            .mappings()
            .all()
        )

    summary = BitcoinSummaryOut(
        release_id=agg["release_id"],
        model_version=(rel or {}).get("model_version", "—"),
        total_scored=agg["total_scored"],
        flagged_illicit=agg["flagged_illicit"],
        requires_review=agg["requires_review"],
        by_level={
            "CRITICAL": agg["lvl_critical"],
            "HIGH": agg["lvl_high"],
            "MEDIUM": agg["lvl_medium"],
            "LOW": agg["lvl_low"],
        },
        illicit_true_total=agg["illicit_true_total"],
        flagged_true_positive=agg["flagged_true_positive"],
        f1=primary.get("f1"),
        precision=primary.get("precision"),
        recall=primary.get("recall"),
        pr_auc=primary.get("pr_auc"),
        test_timestep_min=agg["ts_min"],
        test_timestep_max=agg["ts_max"],
    )
    return BitcoinPageOut(
        summary=summary,
        rows=[
            BitcoinScoredRowOut(
                tx_id=r["tx_id"],
                timestep=r["timestep"],
                illicit_prob=_f(r["illicit_prob"]),
                predicted_label=r["predicted_label"],
                true_label=r["true_label"],
                risk_level=r["risk_level"],
                requires_review=r["requires_review"],
                headline=r["headline"],
                reasons=list(r["reasons"] or []),
                caveat=r["caveat"],
                drivers=[
                    BitcoinDriverOut(
                        name=d["name"],
                        label=d.get("label"),
                        meaningful=bool(d.get("meaningful")),
                        value=float(d.get("value", 0.0)),
                        contribution=float(d.get("contribution", 0.0)),
                    )
                    for d in (r["drivers"] or [])
                ],
                meaningful_push_share=(
                    float(r["meaningful_push_share"]) if r["meaningful_push_share"] is not None else None
                ),
                interpretable_ratio=(float(r["interpretable_ratio"]) if r["interpretable_ratio"] is not None else None),
                explanation_quality=r["explanation_quality"],
                graph_in_degree=r["graph_in_degree"],
                graph_out_degree=r["graph_out_degree"],
                graph_flagged_neighbours=r["graph_flagged_neighbours"],
                graph_known_illicit_neighbours=r["graph_known_illicit_neighbours"],
                graph_neighbours=[
                    BitcoinNeighbourOut(
                        id=n["id"], dir=n["dir"], flag=n.get("flag"), known_illicit=bool(n.get("known_illicit"))
                    )
                    for n in (r["graph_neighbours"] or [])
                ],
                evidence_strength=r["evidence_strength"],
                graph_evidence=r["graph_evidence"] or {},
                evidence_reasons=[
                    EvidenceReasonOut(
                        priority=er.get("priority", 9),
                        badges=list(er.get("badges", [])),
                        title=er.get("title", ""),
                        text=er.get("text", ""),
                    )
                    for er in (r["evidence_reasons"] or [])
                ],
                recommended_steps=list(r["recommended_steps"] or []),
                risk_reasons=[
                    RiskReasonOut(
                        id=rr["id"],
                        category=rr["category"],
                        title=rr["title"],
                        side=rr["side"],
                        feature_ids=rr["feature_ids"],
                        reference=(
                            RiskReasonReference(**rr["reference"]) if rr.get("reference") else None
                        ),
                        shap_direction=rr["shap_direction"],
                        contribution=rr["contribution"],
                        contribution_label=rr["contribution_label"],
                        temporal_availability=rr["temporal_availability"],
                        after_transaction=rr["after_transaction"],
                        investigator_text=rr["investigator_text"],
                    )
                    for rr in build_risk_reasons(
                        list(r["drivers"] or []),
                        int(r["graph_in_degree"] or 0),
                        int(r["graph_out_degree"] or 0),
                        _bitcoin_distribution(),
                    )
                ],
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/fc/projects", response_model=list[ProjectOut])
def projects() -> list[ProjectOut]:
    with get_session() as session:
        rows = (
            session.execute(
                text(
                    """SELECT project_id, name, symbol, chain, contract_address, deployer_address,
                              launched_at, holder_gini, liquidity_usd, liquidity_removed_pct,
                              privileged_functions, kol_channels, domain_age_days, risk_score, status
                         FROM fc.token_project
                        ORDER BY risk_score DESC"""
                )
            )
            .mappings()
            .all()
        )
    return [
        ProjectOut(
            id=r["project_id"],
            name=r["name"],
            symbol=r["symbol"],
            chain=r["chain"],
            contract_address=r["contract_address"],
            deployer_address=r["deployer_address"],
            launched_at=r["launched_at"],
            holder_gini=_f(r["holder_gini"]) if r["holder_gini"] is not None else None,
            liquidity_usd=_f(r["liquidity_usd"]),
            liquidity_removed_pct=_f(r["liquidity_removed_pct"]) if r["liquidity_removed_pct"] is not None else None,
            privileged_functions=list(r["privileged_functions"]),
            kol_channels=r["kol_channels"],
            domain_age_days=r["domain_age_days"],
            risk_score=r["risk_score"],
            status=r["status"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------
# Tác tử AI
#
# Đọc thẳng dấu vết thật của tầng điều tra: ``investigation_agent_run`` (một
# dòng cho mỗi tác tử ở mỗi vòng) và ``investigation_tool_call`` (từng lần gọi
# công cụ). Ba tác tử — điều phối, giải thích, phản biện — chính là ba "tier"
# mà màn hình hiển thị.
# ---------------------------------------------------------------------

_AGENT_RUN_SQL = """
    SELECT r.run_id, r.agent_name, r.iteration, r.status, r.started_at, r.completed_at,
           r.model_provider, r.model_name, r.prompt_version, r.output_summary,
           r.total_token_count, r.duration_ms,
           i.case_id, i.alert_id,
           (SELECT count(*) FROM investigation_tool_call c WHERE c.run_id = r.run_id) AS step_count
      FROM investigation_agent_run r
      JOIN investigation i ON i.investigation_id = r.investigation_id
"""


def _agent_confidence(summary: dict[str, Any]) -> float | None:
    """Độ tin cậy do chính tác tử khai báo; điều phối viên không khai nên trả None."""
    value = summary.get("confidence")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _agent_conclusion(agent_name: str, summary: dict[str, Any]) -> str:
    """Một câu đọc được cho từng loại tác tử.

    Ba tác tử trả ba cấu trúc khác nhau, nên không có trường ``conclusion``
    chung để lấy. Ghép ở đây thay vì bắt giao diện tự đoán cấu trúc.
    """
    if agent_name == "explanation_agent":
        return str(summary.get("summary") or "")

    if agent_name == "evidence_critic":
        status = str(summary.get("status") or "—")
        issues = summary.get("issues")
        unsupported = summary.get("unsupported_claims")
        parts = [f"Phản biện: {status}"]
        if isinstance(issues, list) and issues:
            parts.append(f"{len(issues)} vấn đề")
        if isinstance(unsupported, list) and unsupported:
            parts.append(f"{len(unsupported)} nhận định thiếu căn cứ")
        if summary.get("next_action"):
            parts.append(f"đề xuất: {summary['next_action']}")
        return " · ".join(parts)

    # investigation_supervisor
    decisions = summary.get("decisions")
    count = len(decisions) if isinstance(decisions, list) else 0
    enough = summary.get("evidence_sufficient")
    verdict = "đủ bằng chứng" if enough is True else "chưa đủ bằng chứng" if enough is False else "chưa kết luận"
    return f"Điều phối: chọn {count} công cụ, đánh giá {verdict}"


def _agent_run_out(row: Mapping[str, Any]) -> AgentRunOut:
    summary = row["output_summary"] if isinstance(row["output_summary"], dict) else {}
    return AgentRunOut(
        id=row["run_id"],
        case_id=row["case_id"],
        alert_id=row["alert_id"],
        # Giao diện gọi trường này là "tier". Ở đây nó là tên tác tử — thứ bậc
        # thật của hệ thống là ba tác tử nối tiếp nhau, không phải ba cấp tổ chức.
        tier=row["agent_name"],
        started_at=row["started_at"],
        finished_at=row["completed_at"],
        status=str(row["status"]).lower(),
        model_version=f"{row['model_name']} · {row['prompt_version']}",
        conclusion=_agent_conclusion(row["agent_name"], summary),
        confidence=_agent_confidence(summary),
        # Nhà cung cấp giả lập không trả số token; 0 ở đây nghĩa là "không đo
        # được", và giao diện hiển thị đúng con số đó thay vì bịa ra ước lượng.
        token_cost=int(row["total_token_count"] or 0),
        step_count=int(row["step_count"] or 0),
    )


def _step_input(arguments: Mapping[str, Any] | None) -> str:
    """Gộp tham số gọi công cụ, bỏ những khoá để trống.

    Lược đồ tham số là hợp của mọi công cụ nên mỗi lần gọi chỉ dùng vài khoá,
    phần còn lại là null. In hết ra thì dòng nào cũng dài mười mấy chữ ``null``.
    """
    if not arguments:
        return "không tham số"
    used = {k: v for k, v in arguments.items() if v is not None}
    if not used:
        return "không tham số"
    return ", ".join(f"{k}={v}" for k, v in sorted(used.items()))


def _step_output(result: Mapping[str, Any] | None, status: str, error_type: str | None) -> str:
    if status in {"FAILED", "TIMEOUT"}:
        return f"Không lấy được dữ liệu ({error_type or status})"
    fields = (result or {}).get("result_fields")
    available = (result or {}).get("available")
    if available is False:
        return "Công cụ chạy xong nhưng không có dữ liệu cho phạm vi này"
    if isinstance(fields, list) and fields:
        return f"Trả về {len(fields)} trường: {', '.join(str(f) for f in fields)}"
    return "Trả về kết quả rỗng"


@router.get("/fc/agent-runs", response_model=AgentRunListOut)
def agent_runs(limit: int = Query(default=200, ge=1, le=1000)) -> AgentRunListOut:
    """Danh sách lượt chạy gần nhất (giới hạn `limit`) + TỔNG THẬT của toàn bảng.

    Các số tổng (tổng lần chạy, phản biện, thất bại, token) tính bằng aggregate
    trên cả bảng — KHÔNG đếm số dòng lấy về, nếu không sẽ kẹt ở đúng `limit`.
    """
    with get_session() as session:
        rows = (
            session.execute(
                text(f"{_AGENT_RUN_SQL} ORDER BY r.started_at DESC LIMIT :limit"),
                {"limit": limit},
            )
            .mappings()
            .all()
        )
        summary = session.execute(
            text(
                """SELECT count(*) AS total,
                          count(*) FILTER (WHERE agent_name = 'evidence_critic') AS critic,
                          count(*) FILTER (WHERE status IN ('failed', 'timeout')) AS failed,
                          coalesce(sum(total_token_count), 0) AS tokens
                     FROM investigation_agent_run"""
            )
        ).mappings().one()
    return AgentRunListOut(
        rows=[_agent_run_out(row) for row in rows],
        total=int(summary["total"]),
        critic_count=int(summary["critic"]),
        failed_count=int(summary["failed"]),
        total_tokens=int(summary["tokens"]),
    )


@router.get("/fc/agent-runs/{run_id}", response_model=AgentRunDetailOut)
def agent_run_detail(run_id: str) -> AgentRunDetailOut:
    with get_session() as session:
        run = session.execute(text(f"{_AGENT_RUN_SQL} WHERE r.run_id = :rid"), {"rid": run_id}).mappings().first()
        if not run:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy lần chạy {run_id}")

        steps = (
            session.execute(
                text(
                    """SELECT tool_call_id, tool_name, arguments, result_summary, status,
                              started_at, duration_ms, output_ref, error_type
                         FROM investigation_tool_call
                        WHERE run_id = :rid
                        ORDER BY started_at"""
                ),
                {"rid": run_id},
            )
            .mappings()
            .all()
        )

    base = _agent_run_out(run)
    return AgentRunDetailOut(
        **base.model_dump(exclude={"step_count"}),
        step_count=len(steps),
        steps=[
            AgentStepOut(
                id=s["tool_call_id"],
                index=index,
                tool=s["tool_name"],
                input_summary=_step_input(s["arguments"]),
                output_summary=_step_output(s["result_summary"], s["status"], s["error_type"]),
                status=str(s["status"]).lower(),
                started_at=s["started_at"],
                duration_ms=s["duration_ms"],
                # Mỗi lần gọi sinh đúng một gói bằng chứng, hoặc không sinh gói
                # nào khi thất bại. Bọc thành danh sách cho khớp lược đồ.
                evidence_refs=[s["output_ref"]] if s["output_ref"] else [],
            )
            for index, s in enumerate(steps, start=1)
        ],
    )


# ---------------------------------------------------------------------
# Kiểm định, giám sát, chất lượng
# ---------------------------------------------------------------------

#: Chỉ số lấy ra từ mỗi lượt chạy, theo thứ tự hiển thị.
_BENCHMARK_METRICS = ("f1", "pr_auc", "precision", "recall", "alert_rate")


@router.get("/fc/benchmarks", response_model=list[BenchmarkOut])
def benchmarks() -> list[BenchmarkOut]:
    """Kết quả đánh giá đã ký của nhánh IBM MEGA-PNA (mô hình đồ thị chấm cạnh).

    Màn "Chi tiết ổn định" nói về nhánh IBM MEGA-PNA — mô hình học máy chất lượng
    cao đo trên HI-Medium. TRƯỚC ĐÂY endpoint này đọc release ``status='active'``,
    nhưng release đang phục vụ hàng đợi lại là bộ luật currency-native LI-Small
    (F1 ~0,30) — thấp và không phải MEGA-PNA — nên màn hình hiện nhầm điểm của một
    model khác hẳn tiêu đề. Giờ đọc ĐÚNG nhánh graph_edge_classifier trên IBM
    (fall back về active nếu không có), để con số khớp với nhánh đang trình bày.

    Nguồn là cột ``edge_model_release.benchmark`` — khối JSON đã ký lúc huấn luyện.
    Mỗi hạt giống ngẫu nhiên là một "gói kịch bản" riêng: một con số F1 duy nhất
    không nói được nó ổn định hay ăn may, nên bày cả dải ra.
    """
    with get_session() as session:
        release = (
            session.execute(
                text(
                    """SELECT release_id, model_version, dataset, split, benchmark, threshold, trained_at
                         FROM edge_model_release
                        WHERE benchmark ? 'primary_seed'
                        ORDER BY (coalesce(benchmark->>'model_kind', '') = 'graph_edge_classifier'
                                  AND dataset ILIKE '%IBM%') DESC,
                                 (status = 'active') DESC
                        LIMIT 1"""
                )
            )
            .mappings()
            .first()
        )
    if release is None or not isinstance(release["benchmark"], dict):
        return []

    benchmark = release["benchmark"]
    primary = benchmark.get("primary_seed") or {}
    runs = benchmark.get("over_seeds", {}).get("runs") or []
    if primary and not any(r.get("seed") == primary.get("seed") for r in runs):
        runs = [primary, *runs]

    evaluated_at = release["trained_at"]
    out: list[BenchmarkOut] = []
    for run in runs:
        seed = run.get("seed")
        is_primary = seed == primary.get("seed")
        for metric in _BENCHMARK_METRICS:
            value = run.get(metric)
            if not isinstance(value, (int, float)):
                continue
            out.append(
                BenchmarkOut(
                    id=f"BM-{release['release_id']}-{seed}-{metric}",
                    task_id=f"seed-{seed}" + (" (chính)" if is_primary else ""),
                    scenario_package=release["dataset"],
                    model_version=release["model_version"],
                    split=release["split"],
                    metric_name=metric,
                    metric_value=float(value),
                    # Không có mục tiêu nào được chốt cho bản này, nên không
                    # dựng ra một ngưỡng để mọi dòng đều "đạt". Ô kết luận để
                    # trống là câu trả lời trung thực.
                    target_value=None,
                    evaluated_at=evaluated_at,
                    passed=None,
                )
            )
    return out


@router.get("/fc/model-monitor", response_model=list[ModelMonitorOut])
def model_monitor() -> list[ModelMonitorOut]:
    """Trôi phân phối điểm theo tuần, tính sẵn bởi ``scripts/run_data_quality.py``.

    Trục thời gian là ``occurred_at`` của giao dịch chứ không phải lúc chấm
    điểm: cả 6,1 triệu dòng được chấm trong một lượt, nên trục "lúc chấm" chỉ
    có đúng một điểm và không nói được gì về trôi.
    """
    with get_session() as session:
        rows = (
            session.execute(
                text(
                    """SELECT r.model_version, m.observed_at, m.metric_name, m.metric_value,
                              m.drift_score, m.status
                         FROM model_monitor_metric m
                         JOIN edge_model_release r ON r.release_id = m.release_id
                        ORDER BY m.observed_at, m.metric_name"""
                )
            )
            .mappings()
            .all()
        )
    return [
        ModelMonitorOut(
            model_version=r["model_version"],
            observed_at=r["observed_at"],
            metric_name=r["metric_name"],
            metric_value=_f(r["metric_value"]),
            drift_score=_f(r["drift_score"]) if r["drift_score"] is not None else None,
            status=r["status"],
        )
        for r in rows
    ]


@router.get("/fc/model-branches", response_model=list[ModelBranchOut])
def model_branches() -> list[ModelBranchOut]:
    """Các nhánh phát hiện, mỗi nhánh với benchmark trên đúng vùng nó đặc trưng.

    Vì sao có endpoint riêng thay vì mở rộng /fc/edge-model/release: kiến trúc
    của hệ thống là NHIỀU nhánh song song — IBM (rửa tiền trong ngân hàng),
    SAML-D (xuyên biên giới), sắp tới Elliptic (bitcoin). Mỗi nhánh có model
    và bộ chỉ số riêng, không cộng gộp được. Trả về một danh sách, một phần tử
    một nhánh, để giao diện bày cạnh nhau chứ không trộn thành một con số.

    Đọc từ ``edge_model_release`` (mọi status, không chỉ 'active'): nhánh
    SAML-D geo_rule là 'reference' vì nó không chấm cho hàng đợi chính, nhưng
    vẫn là một nhánh thật cần hiển thị.
    """
    with get_session() as session:
        rows = (
            session.execute(
                text(
                    """SELECT release_id, model_version, dataset, benchmark,
                              transaction_rows, positive_rows, triggered_rows, status
                         FROM edge_model_release
                        WHERE benchmark ? 'model_kind'
                        ORDER BY (status = 'active') DESC, dataset"""
                )
            )
            .mappings()
            .all()
        )

    out: list[ModelBranchOut] = []
    for row in rows:
        b = row["benchmark"] if isinstance(row["benchmark"], dict) else {}
        kind = str(b.get("model_kind", "unknown"))

        points = [
            OperatingPointOut(
                alerts=int(p["alerts"]),
                caught=int(p.get("caught", 0)),
                precision=float(p.get("precision", 0.0)),
                recall=float(p.get("recall", 0.0)),
                lift=float(p["lift"]) if isinstance(p.get("lift"), (int, float)) else None,
            )
            for p in (b.get("operating_points") or [])
            if isinstance(p, dict) and "alerts" in p
        ]

        # Chỉ số đầu bảng chọn theo LOẠI model — hai loại khác nhau thật sự,
        # nên không cố nhét vào cùng một khung F1.
        headline: list[dict[str, Any]] = []
        # RandomForest (Bitcoin) và mạng đồ thị (IBM) đều là bộ phân loại từng
        # giao dịch, nên cùng họ chỉ số F1/PR-AUC — dù đo trên hai vùng khác nhau
        # bằng hai model khác nhau. Gộp hai kind ở đây, không phải để trộn kết
        # quả mà để trình bày cùng một khuôn chỉ số.
        if kind in ("graph_edge_classifier", "random_forest_classifier"):
            primary = b.get("primary_seed") or {}
            for key, label in (("f1", "F1"), ("pr_auc", "PR-AUC"), ("precision", "Precision"), ("recall", "Recall")):
                value = primary.get(key)
                if isinstance(value, (int, float)):
                    headline.append({"label": label, "value": round(float(value), 4), "kind": "ratio"})
        elif kind == "geo_rule_ranker":
            # Bộ xếp hạng: lấy mốc ngân sách 250 cảnh báo làm điểm trình bày —
            # cỡ một ngày rà soát. precision/recall/lift tại đúng mốc đó.
            pick = next((p for p in points if p.alerts == 250), points[0] if points else None)
            if pick:
                headline = [
                    {"label": f"Precision @ {pick.alerts}", "value": round(pick.precision, 4), "kind": "ratio"},
                    {"label": f"Recall @ {pick.alerts}", "value": round(pick.recall, 4), "kind": "ratio"},
                    {"label": f"Lift @ {pick.alerts}", "value": round(pick.lift or 0.0, 2), "kind": "multiple"},
                ]

        out.append(
            ModelBranchOut(
                release_id=row["release_id"],
                dataset=row["dataset"],
                model_version=row["model_version"],
                model_kind=kind,
                region_label=str(b.get("region_label", row["dataset"])),
                region_description=str(b.get("region_description", "")),
                region_rows=_as_int(b.get("region_rows")) or _as_int(row["transaction_rows"]),
                positive_rows=_as_int(b.get("positive_rows")) or _as_int(row["positive_rows"]),
                positive_rate=float(b["positive_rate"]) if isinstance(b.get("positive_rate"), (int, float)) else None,
                triggered_rows=int(row["triggered_rows"]),
                status=row["status"],
                headline=headline,
                operating_points=points,
                note=b.get("note") or None,
                not_comparable_note=b.get("not_comparable_note") or None,
            )
        )
    return out


@router.get("/fc/edge-model/release", response_model=EdgeModelReleaseOut)
def edge_model_release() -> EdgeModelReleaseOut:
    """Audited metadata for the release currently served by the console."""
    with get_session() as session:
        row = (
            session.execute(
                text(
                    """SELECT release_id, model_version, dataset, split,
                              model_sha256, scores_sha256, source_database_sha256,
                              threshold, transaction_rows, positive_rows, triggered_rows,
                              feature_count, benchmark, policy, status, trained_at, activated_at
                         FROM edge_model_release
                        WHERE status='active'
                        LIMIT 1"""
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Chưa có currency-native model release đang hoạt động")
    values = dict(row)
    values["threshold"] = _f(values["threshold"])
    return EdgeModelReleaseOut(**values)


@router.get("/fc/data-quality", response_model=list[DataQualityOut])
def data_quality() -> list[DataQualityOut]:
    with get_session() as session:
        rows = (
            session.execute(
                text(
                    """SELECT check_id, dataset, check_name, dimension, observed_at, pass_rate,
                              threshold, rows_checked, rows_failed, status, detail
                         FROM data_quality_check
                        ORDER BY status DESC, dataset"""
                )
            )
            .mappings()
            .all()
        )
    return [
        DataQualityOut(
            id=r["check_id"],
            dataset=r["dataset"],
            check_name=r["check_name"],
            dimension=r["dimension"],
            observed_at=r["observed_at"],
            pass_rate=_f(r["pass_rate"]),
            threshold=_f(r["threshold"]),
            rows_checked=r["rows_checked"],
            rows_failed=r["rows_failed"],
            status=r["status"],
            detail=r["detail"],
        )
        for r in rows
    ]


@router.get("/fc/observations", response_model=list[ObservationOut])
def observations() -> list[ObservationOut]:
    """Nhật ký mở quyền truy cập bằng chứng.

    Đây là màn hình cho phép kiểm toán viên trả lời câu hỏi "tại thời điểm ra
    quyết định, agent được phép nhìn thấy những gì" — trục chính của cơ chế
    chống rò rỉ ở chương 4.
    """
    with get_session() as session:
        rows = (
            session.execute(
                text(
                    """SELECT observation_event_id, evidence_item_id, observer_role, available_from,
                              acquisition_type, legal_basis_id, redaction_profile, source_confidence,
                              chain_of_custody_id, is_visible_to_model, summary
                         FROM fc.observation_event
                        ORDER BY available_from"""
                )
            )
            .mappings()
            .all()
        )
    return [
        ObservationOut(
            id=r["observation_event_id"],
            evidence_item_id=r["evidence_item_id"],
            observer_role=r["observer_role"],
            available_from=r["available_from"],
            acquisition_type=r["acquisition_type"],
            legal_basis_id=r["legal_basis_id"],
            redaction_profile=r["redaction_profile"],
            source_confidence=_f(r["source_confidence"]),
            chain_of_custody_id=r["chain_of_custody_id"],
            is_visible_to_model=r["is_visible_to_model"],
            summary=r["summary"],
        )
        for r in rows
    ]


@router.get("/fc/sources", response_model=list[SourceOut])
def sources() -> list[SourceOut]:
    """Sổ nguồn dữ liệu, dựng từ chính dấu vết nạp liệu.

    Không có bảng khai báo tay nào ở đây, và đó là chủ ý: một sổ nguồn viết tay
    sẽ lệch khỏi thực tế ngay lần nạp tiếp theo mà không ai biết. Ba nguồn dưới
    đây đọc thẳng từ cột xuất xứ của dữ liệu đã nạp, lô nạp, và bản mô hình đang
    phục vụ — thứ gì không nạp được thì cũng không xuất hiện.
    """
    out: list[SourceOut] = []
    with get_session() as session:
        # Cố tình không GROUP BY trên `transaction`: gộp theo (source_dataset,
        # source_file) buộc quét toàn bộ 6,1 triệu dòng và endpoint này hết giờ
        # trên Cloud SQL. min/max của occurred_at đi qua transaction_time_idx nên
        # gần như tức thì, còn số dòng đã có sẵn trong sổ lô nạp — chính con số
        # mà lô ấy ghi nhận, không phải một ước lượng.
        datasets = (
            session.execute(
                text(
                    """SELECT t.source_dataset, t.source_file,
                              (SELECT min(occurred_at)::date FROM transaction) AS first_day,
                              (SELECT max(occurred_at)::date FROM transaction) AS last_day,
                              (SELECT coalesce(sum(transactions_inserted), 0) FROM behavior_batch) AS rows
                         FROM transaction t
                        WHERE t.source_dataset IS NOT NULL
                        LIMIT 1"""
                )
            )
            .mappings()
            .all()
        )
        batches = (
            session.execute(
                text(
                    """SELECT batch_id, source_name, source_sha256, status, rows_read,
                              rows_rejected, started_at, completed_at
                         FROM behavior_batch
                        ORDER BY started_at DESC"""
                )
            )
            .mappings()
            .all()
        )
        release = (
            session.execute(
                text(
                    """SELECT release_id, model_version, dataset, split, model_sha256,
                              transaction_rows, trained_at
                         FROM edge_model_release
                        WHERE status = 'active'
                        LIMIT 1"""
                )
            )
            .mappings()
            .first()
        )

    for row in datasets:
        out.append(
            SourceOut(
                source_id=row["source_dataset"],
                source_type="dataset",
                scope=f"{row['source_file']} · {row['rows']:,} giao dịch",
                period=f"{row['first_day']} → {row['last_day']}",
                # Bộ dữ liệu IBM là dữ liệu tổng hợp, không gắn với một pháp
                # quyền nào. Ghi "tổng hợp" thay vì bịa ra một quốc gia.
                jurisdiction="tổng hợp (IBM AML)",
                confidence=1.0,
                access_level="internal",
                prohibited_uses="Không dùng để kết luận về khách hàng có thật; đây là dữ liệu mô phỏng công khai.",
            )
        )

    for row in batches:
        rejected = int(row["rows_rejected"] or 0)
        total = int(row["rows_read"] or 0)
        out.append(
            SourceOut(
                source_id=row["batch_id"],
                source_type="ingest_batch",
                scope=f"{row['source_name']} · {total:,} dòng đọc, {rejected:,} bị loại",
                period=f"{row['started_at']:%Y-%m-%d %H:%M} → "
                + (f"{row['completed_at']:%H:%M}" if row["completed_at"] else "chưa xong"),
                jurisdiction=f"sha256 {row['source_sha256'][:16]}…",
                # Lô nạp bị loại dòng nào thì độ tin cậy giảm đúng theo tỷ lệ đó,
                # thay vì gán một con số cảm tính.
                confidence=1.0 if total == 0 else (total - rejected) / total,
                access_level="internal",
                prohibited_uses="Chỉ dùng để truy vết xuất xứ; không phải nguồn số liệu báo cáo.",
            )
        )

    if release is not None:
        out.append(
            SourceOut(
                source_id=release["release_id"],
                source_type="model_release",
                scope=f"{release['model_version']} · {release['transaction_rows']:,} giao dịch đã chấm",
                period=f"{release['dataset']} · tập {release['split']}",
                jurisdiction=f"sha256 {release['model_sha256'][:16]}…",
                confidence=1.0,
                access_level="restricted",
                prohibited_uses="Điểm số của mô hình không phải kết luận; mọi quyết định phải qua người có thẩm quyền.",
            )
        )

    return out


# ---------------------------------------------------------------------
# Transaction Explorer
# ---------------------------------------------------------------------


@router.get("/transactions", response_model=TxPageOut)
def transactions(
    q: str = Query(default="", max_length=64),
    channel: str = Query(default="all", max_length=32),
    min_amount: float = Query(default=0, ge=0),
    min_score: float = Query(default=0, ge=0, le=1),
    currency: str = Query(default="all", max_length=64),
    triggered: bool | None = Query(default=None),
    dataset: str | None = Query(default=None, description="ibm_hi_medium | saml_d"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> TxPageOut:
    """Duyệt giao dịch có phân trang.

    Đếm tổng bằng một truy vấn riêng thay vì `count(*) OVER ()`: trên bảng vài
    triệu dòng, window function buộc phải quét hết ngay cả khi chỉ lấy 50 dòng.

    ``dataset`` lọc theo bộ dữ liệu vận hành. Không lọc thì bảng trộn giao dịch
    IBM và SAML-D, chuyên viên không biết dòng nào thuộc bộ nào. Cột
    ``source_dataset`` lưu tên người đọc nên khớp bằng ILIKE thay vì mã.
    """
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}

    # Hai chế độ duyệt, vì hai nhánh chấm điểm khác nhau về BẢN CHẤT:
    #  • Nhánh đang phục vụ (IBM, chấm từng giao dịch): duyệt ĐÚNG tập đã chấm
    #    của release active — INNER JOIN, giữ nguyên hành vi cũ.
    #  • SAML-D chấm theo hành lang địa lý (geo_rule), KHÔNG có điểm cấp giao
    #    dịch. Ép nó vào khuôn "tập đã chấm" thì ra 0 dòng, trông như hỏng. Nên
    #    duyệt giao dịch SAML-D thô: LEFT JOIN bảng điểm (luôn NULL ở nhánh này),
    #    cột điểm để trống một cách trung thực thay vì bịa số 0.
    saml_browse = dataset == "saml_d"
    # Cột dùng để sắp xếp trang. Mặc định theo thời gian; nhánh IBM đổi thành
    # (source_dataset, occurred_at DESC) để ÉP index tổ hợp (xem chú thích dưới).
    order_by = "t.occurred_at DESC"
    ibm_src: str | None = None
    if saml_browse:
        # So khớp CHÍNH XÁC tên bộ, không ILIKE: giá trị cột là hằng
        # 'SAML-D', và equality mới dùng được chỉ mục thay vì quét cả bảng.
        # SAML-D là bộ MỚI NHẤT nên ORDER BY occurred_at DESC gặp nó trước —
        # không dính bẫy như IBM, giữ nguyên.
        join_sql = """FROM transaction t
                       LEFT JOIN transaction_model_score s ON s.transaction_id = t.transaction_id
                       LEFT JOIN edge_model_release r ON r.release_id = s.release_id"""
        where = ["t.source_dataset = 'SAML-D'"]
    else:
        # IBM (hoặc không chọn): INNER JOIN tập đã chấm của release active.
        #
        # TRƯỚC ĐÂY bảng transaction chỉ có IBM nên không cần lọc source_dataset.
        # Từ khi nạp 9,5M dòng SAML-D (mốc thời gian MỚI HƠN toàn bộ IBM), giả
        # định đó sai: `ORDER BY occurred_at DESC` đi index thời gian sẽ lội qua
        # hết 9,5M dòng SAML-D (không có điểm active-release → bị loại) trước khi
        # chạm 50 dòng IBM → treo ~600s. Khoá theo source_dataset của chính
        # release active (tra một lần, rẻ) để planner dùng index tổ hợp
        # (source_dataset, occurred_at DESC) và chỉ đi trên vùng IBM.
        join_sql = """FROM transaction t
                       JOIN transaction_model_score s USING (transaction_id)
                       JOIN edge_model_release r USING (release_id)"""
        where = ["r.status = 'active'"]
        with get_session() as _probe:
            ibm_src = _probe.execute(
                text(
                    """SELECT t.source_dataset
                         FROM transaction_model_score s
                         JOIN transaction t USING (transaction_id)
                         JOIN edge_model_release r USING (release_id)
                        WHERE r.status = 'active' LIMIT 1"""
                )
            ).scalar()
        if ibm_src:
            # = ANY(ARRAY[...]) thay cho = :src là CỐ Ý: với equality đơn, planner
            # const-fold source_dataset khỏi ORDER BY rồi quay lại dùng index thời
            # gian (lội hết SAML-D mới hơn → treo 600s). Dạng ANY chặn const-fold,
            # nên ORDER BY (source_dataset, occurred_at DESC) khớp và ÉP dùng index
            # tổ hợp transaction_dataset_time_idx → quét đúng vùng IBM (~0,05s).
            where.append("t.source_dataset = ANY(ARRAY[:ibm_src])")
            params["ibm_src"] = ibm_src
            order_by = "t.source_dataset, t.occurred_at DESC"

    if q:
        where.append(
            "(t.source_transaction_id ILIKE :q OR t.from_account_key ILIKE :q "
            "OR t.to_account_key ILIKE :q OR t.remarks ILIKE :q)"
        )
        params["q"] = f"%{q}%"
    if channel != "all":
        where.append("t.channel = :channel")
        params["channel"] = channel
    if min_amount > 0:
        where.append("t.amount >= :min_amount")
        params["min_amount"] = min_amount
    if min_score > 0:
        where.append("s.model_score >= :min_score")
        params["min_score"] = min_score
    if currency != "all":
        where.append("(t.currency = :currency OR t.receiving_currency = :currency)")
        params["currency"] = currency
    if triggered is not None:
        where.append("s.triggered = :triggered")
        params["triggered"] = triggered
    clause = " AND ".join(where)
    real_filters = bool(
        q or channel != "all" or min_amount > 0 or min_score > 0 or currency != "all" or triggered is not None
    )

    with get_session() as session:
        # count(*) chỉ khi thật sự cần: có bộ lọc, hoặc đang duyệt SAML thô (tổng
        # của nó là số dòng thô, không có sẵn trong metadata release). Còn xem IBM
        # trơn thì đọc thẳng `transaction_rows` — tránh đếm 6,75 triệu dòng mỗi
        # lần mở trang, vốn khiến trang mặc định treo ~16 giây.
        #
        # ĐẾM KHÔNG JOIN khi có thể: LEFT JOIN transaction_model_score (6,75M) cho
        # từng dòng chỉ để ĐẾM là vô ích (left-join giữ nguyên số dòng transaction)
        # mà khiến đếm 9,5M dòng SAML-D treo >40s. Chỉ giữ join khi bộ lọc chạm cột
        # điểm (s.model_score / s.triggered) hoặc khi duyệt IBM (clause có r.status).
        needs_score = min_score > 0 or triggered is not None
        count_from = "FROM transaction t" if (saml_browse and not needs_score) else join_sql
        if saml_browse or real_filters:
            total = session.execute(
                text(
                    f"""SELECT count(*)
                           {count_from}
                          WHERE {clause}"""  # noqa: S608
                ),
                params,
            ).scalar_one()
        else:
            total = (
                session.execute(
                    text("SELECT transaction_rows FROM edge_model_release WHERE status='active' LIMIT 1")
                ).scalar_one_or_none()
                or 0
            )

        # Với SAML-D thô (không lọc điểm), LEFT JOIN transaction_model_score LUÔN ra
        # NULL (SAML-D chấm theo geo-rule, không có điểm cấp giao dịch) mà lại khiến
        # planner bỏ index tổ hợp (source_dataset, occurred_at) → sắp xếp 9,5M dòng,
        # treo. Bỏ join, trả NULL cho cột điểm (đúng bản chất) để index chạy tức thì.
        if saml_browse and not needs_score:
            rows_sql = f"""SELECT t.transaction_id, t.source_transaction_id, t.occurred_at,
                               t.from_account_key, t.to_account_key, t.amount, t.currency,
                               t.amount_received, t.receiving_currency, t.channel, t.remarks,
                               NULL::double precision AS model_score,
                               NULL::double precision AS threshold,
                               NULL::boolean AS triggered, NULL::text AS model_version
                          FROM transaction t
                         WHERE {clause}
                         ORDER BY t.occurred_at DESC
                         LIMIT :limit OFFSET :offset"""  # noqa: S608
        else:
            rows_sql = f"""SELECT t.transaction_id, t.source_transaction_id, t.occurred_at,
                               t.from_account_key, t.to_account_key, t.amount, t.currency,
                               t.amount_received, t.receiving_currency, t.channel, t.remarks,
                               s.model_score, s.threshold, s.triggered, r.model_version
                          {join_sql}
                         WHERE {clause}
                         ORDER BY {order_by}
                         LIMIT :limit OFFSET :offset"""  # noqa: S608
        rows = session.execute(text(rows_sql), params).mappings().all()

    return TxPageOut(
        rows=[
            TxRowOut(
                id=r["transaction_id"],
                source_id=r["source_transaction_id"],
                occurred_at=r["occurred_at"],
                from_account=r["from_account_key"],
                to_account=r["to_account_key"],
                amount=_f(r["amount"]),
                currency=r["currency"],
                amount_received=_f(r["amount_received"]),
                receiving_currency=r["receiving_currency"],
                channel=r["channel"],
                remarks=r["remarks"],
                # Để NULL đúng nghĩa "chưa chấm" (SAML-D), không phải điểm 0.
                model_score=_f(r["model_score"]) if r["model_score"] is not None else None,
                threshold=_f(r["threshold"]) if r["threshold"] is not None else None,
                triggered=r["triggered"],
                model_version=r["model_version"],
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


_PATTERN_SQL = """
    SELECT evidence_id, account_key, pattern, detector_version, as_of_time, payload
      FROM graph_detector_evidence
     WHERE account_key = ANY(:accounts)
     ORDER BY (payload ->> 'duration_hours')::float NULLS LAST, evidence_id
     LIMIT :lim
"""


@router.get("/fc/graph/patterns", response_model=list[DetectedPatternOut])
def detected_patterns(
    accounts: str = Query(default="", description="Danh sách account_key, phân tách bằng dấu phẩy"),
    pattern: str | None = Query(default=None, description="CYCLE, FAN_IN, FAN_OUT"),
    limit: int = Query(default=25, le=200),
) -> list[DetectedPatternOut]:
    """Mẫu hình do bộ dò đồ thị tìm được, dựng thành trình tự đọc được.

    Vì sao cần: trang đồ thị đếm chu trình bằng cách dò trên **vùng đang vẽ**, mà
    vùng ấy là lân cận một chặng quanh tài khoản có cảnh báo — 48 đỉnh với 47
    cạnh, tức một cây, nên về mặt toán học không thể có chu trình. Màn hình vì thế
    ghi "Chu trình: 0" trong khi ``graph_detector_evidence`` có 72 chu trình.

    Endpoint này trả đúng những mẫu hình ấy, và **tra thêm số tiền, thời điểm cho
    từng chặng** từ bảng ``transaction``. Danh sách cạnh trần trong payload không
    đủ để chuyên viên đánh giá: thiếu số tiền thì không biết quy mô, thiếu thời
    điểm thì không biết tiền nằm lại bao lâu — mà đó mới là dấu hiệu.
    """
    keys = [item.strip() for item in accounts.split(",") if item.strip()]
    if not keys:
        return []

    with get_session() as session:
        rows = session.execute(text(_PATTERN_SQL), {"accounts": keys, "lim": limit}).mappings().all()
        # `isinstance` chứ không chỉ truthy: gọi hàm trực tiếp trong script thì
        # tham số mặc định là đối tượng ``Query``, vốn truthy, và ``.upper()`` nổ.
        # Qua HTTP thì FastAPI đã thay bằng None, nhưng đường gọi trực tiếp là
        # đường người ta hay dùng để kiểm nhanh.
        if isinstance(pattern, str) and pattern:
            rows = [row for row in rows if row["pattern"] == pattern.upper()]
        if not rows:
            return []

        tx_ids = {
            str(edge.get("transaction_id"))
            for row in rows
            for edge in (row["payload"] or {}).get("edges", [])
            if edge.get("transaction_id")
        }
        detail: dict[str, Any] = {}
        if tx_ids:
            # Bộ dò đồ thị ghi khoá chính BIGINT của bảng ``transaction``, không
            # phải ``source_transaction_id`` (mã băm của dòng gốc IBM). Nối nhầm
            # cột cho ra 0 dòng khớp và mọi chặng mất số tiền lẫn thời điểm.
            numeric = [int(value) for value in tx_ids if value.isdigit()]
            if numeric:
                detail = {
                    str(item["transaction_id"]): item
                    for item in session.execute(
                        text(
                            """SELECT transaction_id, occurred_at, amount, currency
                                 FROM "transaction" WHERE transaction_id = ANY(:ids)"""
                        ),
                        {"ids": numeric},
                    )
                    .mappings()
                    .all()
                }

    results: list[DetectedPatternOut] = []
    for row in rows:
        payload = row["payload"] or {}
        edges = payload.get("edges", [])
        hops: list[PatternHopOut] = []
        previous: datetime | None = None
        # Sắp theo thời gian, không theo thứ tự payload: trình tự chỉ có nghĩa khi
        # đọc đúng chiều thời gian, và bộ dò không cam kết thứ tự nào.
        ordered = sorted(
            edges,
            key=lambda e: detail.get(str(e.get("transaction_id")), {}).get("occurred_at") or datetime.max,
        )
        for index, edge in enumerate(ordered, start=1):
            info = detail.get(str(edge.get("transaction_id")), {})
            when = info.get("occurred_at")
            gap = None
            if when is not None and previous is not None:
                gap = round((when - previous).total_seconds() / 3600, 2)
            if when is not None:
                previous = when
            hops.append(
                PatternHopOut(
                    seq=index,
                    source=str(edge.get("from", "")),
                    target=str(edge.get("to", "")),
                    transaction_id=str(edge.get("transaction_id", "")),
                    occurred_at=when,
                    amount=_f(info["amount"]) if info.get("amount") is not None else None,
                    currency=info.get("currency"),
                    gap_hours=gap,
                )
            )
        results.append(
            DetectedPatternOut(
                evidence_id=row["evidence_id"],
                pattern=row["pattern"],
                account_key=row["account_key"],
                accounts=list(payload.get("accounts", [])),
                hop_count=len(hops),
                duration_hours=payload.get("duration_hours"),
                detector_version=row["detector_version"],
                as_of_time=row["as_of_time"],
                hops=hops,
            )
        )
    return results


@router.get("/fc/graph/narrative", response_model=GraphNarrativeOut)
async def graph_narrative(
    account_key: str = Query(min_length=3, max_length=128),
    window_days: int = Query(default=30, ge=1, le=90),
) -> GraphNarrativeOut:
    """Đọc hộ chuyên viên vùng đồ thị quanh một tài khoản.

    Vì sao cần: màn hình đồ thị vẽ đúng nhưng không nói gì. Người rà soát nhìn
    vào một mớ đỉnh và mũi tên rồi phải tự trả lời tiền vào từ đâu, tiền đi đâu,
    ai đứng giữa, vì sao chỗ này đáng nghi và nên nhìn vào đâu trước. Không ai
    làm được việc đó trong vài phút, nên cả màn hình trở thành trang trí.

    Mốc thời gian là giao dịch gần nhất của chính tài khoản, không phải giờ hệ
    thống. Dữ liệu là lịch sử: neo vào ``now()`` thì cửa sổ nằm hoàn toàn sau
    giao dịch cuối cùng và mọi phép đo trả về 0.
    """
    with get_session() as session:
        as_of = session.execute(
            text(
                """SELECT max(occurred_at) FROM transaction
                    WHERE from_account_key = :account OR to_account_key = :account"""
            ),
            {"account": account_key},
        ).scalar_one_or_none()
        if as_of is None:
            raise HTTPException(status_code=404, detail=f"Không có giao dịch nào của tài khoản {account_key}")
        reading = read_neighbourhood(session, account_key, as_of=as_of, window_days=window_days)

    narrative, source = await narrate(reading)
    return GraphNarrativeOut(
        account_key=account_key,
        window_start=reading["window_start"],
        window_end=reading["window_end"],
        flow_in=narrative.flow_in,
        flow_out=narrative.flow_out,
        why_suspicious=narrative.why_suspicious,
        how_to_read=narrative.how_to_read,
        source=source,
        reading=reading,
    )


@router.post("/fc/bitcoin/{tx_id}/explain")
async def explain_bitcoin(tx_id: str):
    """Giải thích ngôn ngữ tự nhiên (Gemini) cho MỘT giao dịch — gọi ON-DEMAND.

    KHÔNG precompute 67k lệnh LLM: chỉ chạy khi chuyên viên bấm "AI giải thích".
    Agent CHỈ diễn đạt lại structured evidence đã chấm (RF + TreeSHAP + registry
    phục hồi + graph), rào chắn §37 ở system prompt + schema. Trả 503 nếu chưa
    cấu hình GOOGLE_API_KEY (giao diện hiển thị trạng thái, không treo).
    """
    from src.bitcoin_aml.agent import explain as _explain
    from src.investigation.llm import gemini_is_configured, get_gemini_service

    with get_session() as session:
        row = (
            session.execute(
                text(
                    """SELECT tx_id, timestep, illicit_prob, risk_level, explanation_quality,
                              true_label, headline, drivers, graph_evidence, recommended_steps
                         FROM bitcoin_scored_tx WHERE tx_id = :id"""
                ),
                {"id": tx_id},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Không thấy giao dịch {tx_id}")
    if not gemini_is_configured():
        raise HTTPException(status_code=503, detail="Agent Gemini chưa cấu hình (GOOGLE_API_KEY).")

    record = dict(row)
    record["illicit_prob"] = float(record["illicit_prob"])
    service = get_gemini_service()
    try:
        result = await _explain(service, record)
    except Exception as exc:  # noqa: BLE001 - lỗi LLM → 502 rõ ràng, không treo giao diện
        raise HTTPException(status_code=502, detail=f"Agent lỗi khi giải thích: {exc}") from exc
    finally:
        await service.close()
    return result.model_dump()
