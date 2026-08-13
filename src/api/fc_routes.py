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

from typing import Any, Literal, NamedTuple

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.db.session import get_session
from src.models.fc_schemas import (
    AgentRunDetailOut,
    AgentRunOut,
    AgentStepOut,
    BenchmarkOut,
    CryptoOut,
    CryptoTransferOut,
    DataQualityOut,
    ExposureOut,
    FlowOut,
    GraphEdgeOut,
    GraphNodeOut,
    GraphOut,
    HubOut,
    ModelMonitorOut,
    NavCountsOut,
    ObservationOut,
    ProjectOut,
    SearchHitOut,
    SourceOut,
    TxPageOut,
    TxRowOut,
    WorldOut,
)

router = APIRouter()


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
async def nav_counts() -> NavCountsOut:
    """Số việc tồn đọng hiển thị trên badge sidebar."""
    with get_session() as session:
        row = (
            session.execute(
                text(
                    """WITH latest AS (
                           SELECT batch_id FROM behavior_batch
                            WHERE status = 'completed'
                            ORDER BY completed_at DESC NULLS LAST LIMIT 1
                       )
                       SELECT
                         (SELECT count(*) FROM alert al
                           WHERE status <> 'closed' AND EXISTS (
                               SELECT 1 FROM detection_result d
                                WHERE d.alert_id = al.alert_id
                                  AND d.batch_id = (SELECT batch_id FROM latest)))  AS alerts,
                         (SELECT count(*) FROM approval ap
                           JOIN sar_draft sd USING (sar_draft_id)
                           WHERE ap.decision = 'pending' AND EXISTS (
                               SELECT 1 FROM alert al JOIN detection_result d USING (alert_id)
                                WHERE al.case_id = sd.case_id
                                  AND d.batch_id = (SELECT batch_id FROM latest)))  AS approvals,
                         (SELECT count(*) FROM alert al
                           WHERE status <> 'closed' AND risk_score >= 80 AND EXISTS (
                               SELECT 1 FROM detection_result d
                                WHERE d.alert_id = al.alert_id
                                  AND d.batch_id = (SELECT batch_id FROM latest)))  AS critical"""
                )
            )
            .mappings()
            .one()
        )
    return NavCountsOut(**dict(row))


@router.get("/search", response_model=list[SearchHitOut])
async def search(q: str = Query(min_length=2, max_length=64)) -> list[SearchHitOut]:
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
                          SELECT 1 FROM detection_result d
                           WHERE d.alert_id = alert.alert_id
                             AND d.batch_id = (
                                 SELECT batch_id FROM behavior_batch
                                  WHERE status = 'completed'
                                  ORDER BY completed_at DESC NULLS LAST LIMIT 1
                             )
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
                      AND EXISTS (
                          SELECT 1 FROM alert al JOIN detection_result d USING (alert_id)
                           WHERE al.case_id = aml_case.case_id
                             AND d.batch_id = (
                                 SELECT batch_id FROM behavior_batch
                                  WHERE status = 'completed'
                                  ORDER BY completed_at DESC NULLS LAST LIMIT 1
                             )
                      )
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


# Tài khoản kèm quốc gia, dùng lại ở cả hai truy vấn bên dưới. Không có khoá
# ngoại giữa `account` và `bank`, nên đây là INNER JOIN có chủ đích: tài khoản
# chưa biết ngân hàng thì không lên bản đồ, và phần thiếu được nêu ở `limitation`.
_ACCOUNT_COUNTRY = """
    SELECT a.account_key, b.country_code, b.is_vasp
      FROM account a JOIN bank b ON b.bank_code = a.bank_code
     WHERE b.country_code IS NOT NULL
"""

_MAX_FLOWS = 300


def _operational_geography(session: Any) -> _Geography:
    """Hub và hành lang dòng tiền dựng từ dữ liệu vận hành thật.

    Trả về bản đồ rỗng nếu chưa chạy `scripts/load_bank_geography.py` — không
    dựng bản đồ nửa vời từ dữ liệu chưa nạp.
    """
    if not session.execute(text("SELECT EXISTS (SELECT 1 FROM bank)")).scalar_one():
        return _Geography(
            hubs=[],
            flows=[],
            limitation=(
                "Chưa nạp địa lý ngân hàng. Chạy scripts/load_bank_geography.py để "
                "suy quốc gia từ tên ngân hàng trong *_accounts.csv."
            ),
        )

    hub_rows = (
        session.execute(
            text(
                f"""
                WITH acct AS ({_ACCOUNT_COUNTRY}),
                edge AS (
                    SELECT af.country_code AS src, ad.country_code AS dst, t.amount
                      FROM transaction t
                      JOIN acct af ON af.account_key = t.from_account_key
                      JOIN acct ad ON ad.account_key = t.to_account_key
                ),
                outb AS (SELECT src AS cc, count(*) AS n, sum(amount) AS v FROM edge GROUP BY 1),
                inb  AS (SELECT dst AS cc, count(*) AS n, sum(amount) AS v FROM edge GROUP BY 1),
                ent  AS (SELECT country_code AS cc, count(*) AS n FROM acct GROUP BY 1),
                alr  AS (
                    SELECT ac.country_code AS cc, count(*) AS n, avg(al.risk_score) AS r
                      FROM alert al JOIN acct ac ON ac.account_key = al.account_key
                     GROUP BY 1
                )
                SELECT g.country_code, g.name, g.lat, g.lon,
                       ent.n AS entities,
                       coalesce(inb.n, 0) AS inbound,
                       coalesce(outb.n, 0) AS outbound,
                       coalesce(inb.v, 0) + coalesce(outb.v, 0) AS volume_usd,
                       coalesce(alr.n, 0) AS alerts,
                       coalesce(round(alr.r), 0) AS risk_score
                  FROM country_geo g
                  JOIN ent  ON ent.cc  = g.country_code
                  LEFT JOIN inb  ON inb.cc  = g.country_code
                  LEFT JOIN outb ON outb.cc = g.country_code
                  LEFT JOIN alr  ON alr.cc  = g.country_code
                 ORDER BY volume_usd DESC
                """
            )
        )
        .mappings()
        .all()
    )

    flow_rows = (
        session.execute(
            text(
                f"""
                WITH acct AS ({_ACCOUNT_COUNTRY}),
                edge AS (
                    -- `channel` của giao diện là loại kênh dòng tiền
                    -- (bank/p2p/vasp/chain/gamb/proj), không phải hình thức
                    -- thanh toán. Bộ IBM chỉ có ACH/Cash/Cheque/Credit Card/Wire
                    -- — đều là kênh ngân hàng; trả nguyên giá trị đó ra thì bản
                    -- đồ 3D tra bảng màu không thấy và ném lỗi.
                    SELECT af.country_code AS src, ad.country_code AS dst,
                           CASE WHEN af.is_vasp OR ad.is_vasp THEN 'vasp' ELSE 'bank' END AS channel,
                           t.from_account_key, t.amount, t.currency, t.occurred_at
                      FROM transaction t
                      JOIN acct af ON af.account_key = t.from_account_key
                      JOIN acct ad ON ad.account_key = t.to_account_key
                     WHERE af.country_code <> ad.country_code
                ),
                alr AS (
                    SELECT e.src, e.dst, e.currency,
                           count(DISTINCT al.alert_id) AS n,
                           coalesce(round(avg(al.risk_score)), 0) AS r
                      FROM edge e JOIN alert al ON al.account_key = e.from_account_key
                     GROUP BY 1, 2, 3
                )
                SELECT e.src, e.dst, e.currency,
                       mode() WITHIN GROUP (ORDER BY e.channel) AS channel,
                       count(*) AS txn_count,
                       sum(e.amount) AS volume_usd,
                       min(e.occurred_at) AS first_seen,
                       max(e.occurred_at) AS last_seen,
                       coalesce(max(alr.n), 0) AS alert_count,
                       coalesce(max(alr.r), 0) AS risk_score
                  FROM edge e
                  LEFT JOIN alr ON alr.src = e.src AND alr.dst = e.dst AND alr.currency = e.currency
                 GROUP BY e.src, e.dst, e.currency
                 ORDER BY txn_count DESC
                 LIMIT :limit
                """
            ),
            {"limit": _MAX_FLOWS},
        )
        .mappings()
        .all()
    )

    coverage = (
        session.execute(
            text(
                """SELECT count(*) AS total,
                          count(b.country_code) AS located,
                          count(*) FILTER (WHERE b.country_source = 'assigned') AS assigned
                     FROM account a LEFT JOIN bank b ON b.bank_code = a.bank_code"""
            )
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
            volume_usd=float(row["volume_usd"]),
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
            volume_usd=float(row["volume_usd"]),
            txn_count=int(row["txn_count"]),
            risk_score=int(row["risk_score"]),
            typology_hint=None,
            alert_count=int(row["alert_count"]),
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
        )
        for row in flow_rows
        if row["src"] in coords and row["dst"] in coords
    ]

    total = int(coverage["total"]) or 1
    located = int(coverage["located"])
    assigned = int(coverage["assigned"])
    limitation = (
        f"Quốc gia suy ra từ tên ngân hàng: {located:,}/{total:,} tài khoản có quốc gia "
        f"({located / total:.1%}), trong đó {assigned / total:.1%} là quốc gia do dự án gán "
        "cho ngân hàng hư cấu chứ không đọc được từ dữ liệu. Chưa gán mức rủi ro pháp vực."
    )
    return _Geography(hubs=hubs, flows=flows, limitation=limitation)


@router.get("/world", response_model=WorldOut)
async def world(mode: Literal["operational", "simulation"] = "operational") -> WorldOut:
    """Trung tâm tài chính và hành lang dòng tiền.

    Mặc định chỉ trả dữ liệu vận hành. Batch Behaviour hiện có bank/account ID
    nhưng không có country code hay toạ độ, vì vậy API công bố giới hạn và trả
    bản đồ rỗng thay vì ghép nhầm dữ liệu mô phỏng Việt Nam. Chế độ simulation
    phải được yêu cầu tường minh.
    """
    with get_session() as session:
        if mode == "operational":
            batch = (
                session.execute(
                    text(
                        """SELECT b.batch_id, b.source_name,
                                  count(t.transaction_id) AS transaction_count
                             FROM behavior_batch b
                             LEFT JOIN transaction t ON t.behavior_batch_id = b.batch_id
                            WHERE b.status = 'completed'
                            GROUP BY b.batch_id, b.source_name, b.completed_at
                            ORDER BY b.completed_at DESC NULLS LAST
                            LIMIT 1"""
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
                limitation=(
                    geography.limitation
                    if batch
                    else "Chưa có batch giao dịch vận hành hoàn tất."
                ),
            )

        sim = _current_simulation(session)
        if not sim:
            return WorldOut(
                hubs=[],
                flows=[],
                simulation_id=None,
                scenario_package=None,
                data_mode="simulation",
                source_id=None,
                source_name=None,
                transaction_count=0,
                geography_available=False,
                limitation="Chưa có lần chạy mô phỏng ABM.",
            )

        flows = (
            session.execute(
                text(
                    """SELECT c.corridor_id, c.source_hub_id, c.target_hub_id,
                              s.name AS source_name, t.name AS target_name,
                              s.lat AS slat, s.lon AS slon, t.lat AS tlat, t.lon AS tlon,
                              c.channel, c.currency, c.volume_usd, c.txn_count,
                              c.risk_score, c.typology_hint, c.alert_count,
                              c.first_seen, c.last_seen
                         FROM fc.corridor_flow c
                         JOIN fc.hub s ON s.hub_id = c.source_hub_id
                         JOIN fc.hub t ON t.hub_id = c.target_hub_id
                        WHERE c.simulation_id = :sid
                        ORDER BY c.risk_score DESC, c.volume_usd DESC"""
                ),
                {"sid": sim["simulation_id"]},
            )
            .mappings()
            .all()
        )

        hubs = (
            session.execute(
                text(
                    """SELECT h.hub_id, h.name, h.country_code, h.lat, h.lon, h.jurisdiction_risk,
                              (SELECT count(*) FROM fc.corridor_flow f
                                WHERE f.target_hub_id = h.hub_id AND f.simulation_id = :sid) AS inbound,
                              (SELECT count(*) FROM fc.corridor_flow f
                                WHERE f.source_hub_id = h.hub_id AND f.simulation_id = :sid) AS outbound,
                              (SELECT coalesce(sum(f.volume_usd), 0) FROM fc.corridor_flow f
                                WHERE (f.source_hub_id = h.hub_id OR f.target_hub_id = h.hub_id)
                                  AND f.simulation_id = :sid) AS volume_usd,
                              (SELECT coalesce(sum(f.alert_count), 0) FROM fc.corridor_flow f
                                WHERE (f.source_hub_id = h.hub_id OR f.target_hub_id = h.hub_id)
                                  AND f.simulation_id = :sid) AS alerts,
                              (SELECT count(*) FROM fc.entity e
                                WHERE e.hub_id = h.hub_id AND e.simulation_id = :sid) AS entities,
                              (SELECT coalesce(max(f.risk_score), 0) FROM fc.corridor_flow f
                                WHERE (f.source_hub_id = h.hub_id OR f.target_hub_id = h.hub_id)
                                  AND f.simulation_id = :sid) AS risk_score
                         FROM fc.hub h
                        ORDER BY volume_usd DESC"""
                ),
                {"sid": sim["simulation_id"]},
            )
            .mappings()
            .all()
        )

    return WorldOut(
        simulation_id=sim["simulation_id"],
        scenario_package=sim["scenario_package"],
        data_mode="simulation",
        source_id=sim["simulation_id"],
        source_name=sim["scenario_package"],
        transaction_count=sum(int(f["txn_count"]) for f in flows),
        geography_available=True,
        limitation="Dữ liệu địa lý do mô phỏng ABM sinh, không phải giao dịch của batch vận hành.",
        hubs=[
            HubOut(
                id=h["hub_id"],
                name=h["name"],
                country=h["country_code"],
                lat=_f(h["lat"]),
                lon=_f(h["lon"]),
                jurisdiction_risk=h["jurisdiction_risk"],
                inbound=h["inbound"],
                outbound=h["outbound"],
                volume_usd=_f(h["volume_usd"]),
                alerts=h["alerts"],
                entities=h["entities"],
                risk_score=h["risk_score"],
            )
            for h in hubs
        ],
        flows=[
            FlowOut(
                id=f["corridor_id"],
                source_hub=f["source_hub_id"],
                target_hub=f["target_hub_id"],
                source_name=f["source_name"],
                target_name=f["target_name"],
                slat=_f(f["slat"]),
                slon=_f(f["slon"]),
                tlat=_f(f["tlat"]),
                tlon=_f(f["tlon"]),
                channel=f["channel"],
                currency=f["currency"],
                volume_usd=_f(f["volume_usd"]),
                txn_count=f["txn_count"],
                risk_score=f["risk_score"],
                typology_hint=f["typology_hint"],
                alert_count=f["alert_count"],
                first_seen=f["first_seen"],
                last_seen=f["last_seen"],
            )
            for f in flows
        ],
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



@router.get("/fc/graph", response_model=GraphOut)
async def entity_graph(
    limit: int = Query(default=400, le=2000),
) -> GraphOut:
    """Toàn bộ đồ thị thực thể của lần chạy mô phỏng gần nhất."""
    with get_session() as session:
        sim = _current_simulation(session)
        if not sim:
            return GraphOut(nodes=[], edges=[])

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
async def edge_transactions(
    edge_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    min_amount: float = Query(default=0, ge=0),
    currency: str = Query(default="all", max_length=8),
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
            raise HTTPException(status_code=404, detail="Chưa có lần chạy mô phỏng nào.")

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
async def node_transactions(
    node_id: str,
    direction: Literal["all", "in", "out"] = Query(default="all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> TxPageOut:
    """Giao dịch của một thực thể, cả hai chiều hoặc một chiều."""
    with get_session() as session:
        sim = _current_simulation(session)
        if not sim:
            raise HTTPException(status_code=404, detail="Chưa có lần chạy mô phỏng nào.")

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
async def crypto(limit: int = Query(default=200, le=1000)) -> CryptoOut:
    with get_session() as session:
        sim = _current_simulation(session)
        if not sim:
            return CryptoOut(transfers=[], exposures=[], total_usd=0)

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


@router.get("/fc/projects", response_model=list[ProjectOut])
async def projects() -> list[ProjectOut]:
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
# Agent
# ---------------------------------------------------------------------


@router.get("/fc/agent-runs", response_model=list[AgentRunOut])
async def agent_runs() -> list[AgentRunOut]:
    with get_session() as session:
        rows = (
            session.execute(
                text(
                    """SELECT r.run_id, r.case_id, r.alert_id, r.agent_tier, r.started_at,
                              r.finished_at, r.status, r.model_version, r.conclusion,
                              r.confidence, r.token_cost,
                              (SELECT count(*) FROM fc.agent_step s WHERE s.run_id = r.run_id) AS step_count
                         FROM fc.agent_run r
                        ORDER BY r.started_at DESC"""
                )
            )
            .mappings()
            .all()
        )
    return [
        AgentRunOut(
            id=r["run_id"],
            case_id=r["case_id"],
            alert_id=r["alert_id"],
            tier=r["agent_tier"],
            started_at=r["started_at"],
            finished_at=r["finished_at"],
            status=r["status"],
            model_version=r["model_version"],
            conclusion=r["conclusion"],
            confidence=_f(r["confidence"]) if r["confidence"] is not None else None,
            token_cost=r["token_cost"],
            step_count=r["step_count"],
        )
        for r in rows
    ]


@router.get("/fc/agent-runs/{run_id}", response_model=AgentRunDetailOut)
async def agent_run_detail(run_id: str) -> AgentRunDetailOut:
    with get_session() as session:
        run = (
            session.execute(
                text(
                    """SELECT run_id, case_id, alert_id, agent_tier, started_at, finished_at,
                              status, model_version, conclusion, confidence, token_cost
                         FROM fc.agent_run WHERE run_id = :rid"""
                ),
                {"rid": run_id},
            )
            .mappings()
            .first()
        )
        if not run:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy lần chạy {run_id}")

        steps = (
            session.execute(
                text(
                    """SELECT step_id, step_index, tool_name, input_summary, output_summary,
                              status, started_at, duration_ms, evidence_refs
                         FROM fc.agent_step
                        WHERE run_id = :rid
                        ORDER BY step_index"""
                ),
                {"rid": run_id},
            )
            .mappings()
            .all()
        )

    return AgentRunDetailOut(
        id=run["run_id"],
        case_id=run["case_id"],
        alert_id=run["alert_id"],
        tier=run["agent_tier"],
        started_at=run["started_at"],
        finished_at=run["finished_at"],
        status=run["status"],
        model_version=run["model_version"],
        conclusion=run["conclusion"],
        confidence=_f(run["confidence"]) if run["confidence"] is not None else None,
        token_cost=run["token_cost"],
        step_count=len(steps),
        steps=[
            AgentStepOut(
                id=s["step_id"],
                index=s["step_index"],
                tool=s["tool_name"],
                input_summary=s["input_summary"],
                output_summary=s["output_summary"],
                status=s["status"],
                started_at=s["started_at"],
                duration_ms=s["duration_ms"],
                evidence_refs=list(s["evidence_refs"]),
            )
            for s in steps
        ],
    )


# ---------------------------------------------------------------------
# Kiểm định, giám sát, chất lượng
# ---------------------------------------------------------------------

# Với các chỉ số này, giá trị *thấp* mới là đạt.
_LOWER_IS_BETTER = {"false_positive_rate_hard_negative", "psi_amount", "p95_latency_ms"}


@router.get("/fc/benchmarks", response_model=list[BenchmarkOut])
async def benchmarks() -> list[BenchmarkOut]:
    with get_session() as session:
        rows = (
            session.execute(
                text(
                    """SELECT result_id, task_id, scenario_package, model_version, split,
                              metric_name, metric_value, target_value, evaluated_at
                         FROM fc.benchmark_result
                        ORDER BY scenario_package, metric_name"""
                )
            )
            .mappings()
            .all()
        )

    out: list[BenchmarkOut] = []
    for r in rows:
        target = _f(r["target_value"]) if r["target_value"] is not None else None
        value = _f(r["metric_value"])
        passed: bool | None = None
        if target is not None:
            passed = value <= target if r["metric_name"] in _LOWER_IS_BETTER else value >= target
        out.append(
            BenchmarkOut(
                id=r["result_id"],
                task_id=r["task_id"],
                scenario_package=r["scenario_package"],
                model_version=r["model_version"],
                split=r["split"],
                metric_name=r["metric_name"],
                metric_value=value,
                target_value=target,
                evaluated_at=r["evaluated_at"],
                passed=passed,
            )
        )
    return out


@router.get("/fc/model-monitor", response_model=list[ModelMonitorOut])
async def model_monitor() -> list[ModelMonitorOut]:
    with get_session() as session:
        rows = (
            session.execute(
                text(
                    """SELECT model_version, observed_at, metric_name, metric_value,
                              drift_score, status
                         FROM fc.model_monitor
                        ORDER BY observed_at, metric_name"""
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


@router.get("/fc/data-quality", response_model=list[DataQualityOut])
async def data_quality() -> list[DataQualityOut]:
    with get_session() as session:
        rows = (
            session.execute(
                text(
                    """SELECT check_id, dataset, check_name, dimension, observed_at, pass_rate,
                              threshold, rows_checked, rows_failed, status, detail
                         FROM fc.data_quality_check
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
async def observations() -> list[ObservationOut]:
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
async def sources() -> list[SourceOut]:
    with get_session() as session:
        rows = (
            session.execute(
                text(
                    """SELECT source_id, source_type, scope, period, jurisdiction, confidence,
                              access_level, prohibited_uses
                         FROM fc.source_registry
                        ORDER BY confidence DESC"""
                )
            )
            .mappings()
            .all()
        )
    return [SourceOut(**{k: (_f(v) if k == "confidence" else v) for k, v in dict(r).items()}) for r in rows]


# ---------------------------------------------------------------------
# Transaction Explorer
# ---------------------------------------------------------------------


@router.get("/transactions", response_model=TxPageOut)
async def transactions(
    q: str = Query(default="", max_length=64),
    channel: str = Query(default="all", max_length=32),
    min_amount: float = Query(default=0, ge=0),
    source: Literal["operational", "all"] = Query(default="operational"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> TxPageOut:
    """Duyệt giao dịch có phân trang.

    Đếm tổng bằng một truy vấn riêng thay vì `count(*) OVER ()`: trên bảng vài
    triệu dòng, window function buộc phải quét hết ngay cả khi chỉ lấy 50 dòng.
    """
    where = ["1 = 1"]
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}

    if q:
        where.append("(t.from_account_key ILIKE :q OR t.to_account_key ILIKE :q OR t.remarks ILIKE :q)")
        params["q"] = f"%{q}%"
    if channel != "all":
        where.append("t.channel = :channel")
        params["channel"] = channel
    if min_amount > 0:
        where.append("t.amount >= :min_amount")
        params["min_amount"] = min_amount
    if source == "operational":
        where.append(
            """t.behavior_batch_id = (
                   SELECT batch_id FROM behavior_batch
                    WHERE status = 'completed'
                    ORDER BY completed_at DESC NULLS LAST LIMIT 1
               )"""
        )

    clause = " AND ".join(where)

    with get_session() as session:
        total = session.execute(
            text(f"SELECT count(*) FROM transaction t WHERE {clause}"),  # noqa: S608 — clause dựng từ hằng số
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
