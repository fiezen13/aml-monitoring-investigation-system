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

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

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
                    """SELECT
                         (SELECT count(*) FROM alert WHERE status <> 'closed')      AS alerts,
                         (SELECT count(*) FROM approval WHERE decision = 'pending') AS approvals,
                         (SELECT count(*) FROM alert
                           WHERE status <> 'closed' AND risk_score >= 80)           AS critical"""
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
                    WHERE lower(case_id) LIKE :like OR lower(title) LIKE :like
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

        # Thực thể mô phỏng chỉ tồn tại khi đã chạy generator; bọc để console
        # vẫn hoạt động trên cơ sở dữ liệu chưa có schema fc.
        try:
            for row in session.execute(
                text(
                    """SELECT entity_id, label, entity_type FROM fc.entity
                        WHERE lower(label) LIKE :like OR lower(entity_id) LIKE :like
                        ORDER BY risk_score DESC LIMIT 5"""
                ),
                {"like": like},
            ).mappings():
                hits.append(
                    SearchHitOut(
                        id=row["entity_id"],
                        label=row["label"],
                        kind=row["entity_type"],
                        href=f"/network?focus={row['entity_id']}",
                    )
                )
        except Exception:  # noqa: BLE001 — chưa áp migration 005 thì bỏ qua nhóm này
            pass

    return hits


# ---------------------------------------------------------------------
# World Monitor
# ---------------------------------------------------------------------


@router.get("/world", response_model=WorldOut)
async def world() -> WorldOut:
    """Trung tâm tài chính và hành lang dòng tiền.

    Số liệu của mỗi trung tâm được tổng hợp *từ* các hành lang chứ không lưu
    sẵn: nếu lưu sẵn thì hai nơi sẽ lệch nhau ngay lần sinh dữ liệu tiếp theo.
    """
    with get_session() as session:
        sim = _current_simulation(session)
        if not sim:
            return WorldOut(hubs=[], flows=[], simulation_id=None, scenario_package=None)

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
                    """SELECT source_id, target_id, kind, label, amount_usd,
                              is_inferred, confidence, inference_logic, known_from
                         FROM fc.relationship
                        WHERE simulation_id = :sid"""
                ),
                {"sid": sim["simulation_id"]},
            )
            .mappings()
            .all()
        )

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
                s=e["source_id"],
                t=e["target_id"],
                kind=e["kind"],
                label=e["label"],
                amt=_f(e["amount_usd"]) if e["amount_usd"] is not None else None,
                inferred=e["is_inferred"],
                conf=_f(e["confidence"]) if e["confidence"] is not None else None,
                logic=e["inference_logic"],
                known_from=e["known_from"],
            )
            for e in edges
            if e["source_id"] in ids and e["target_id"] in ids
        ],
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
