from __future__ import annotations

import json
import math
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import get_settings
from src.investigation.repository import InvestigationRepository
from src.investigation.schemas import (
    AnomalousFeature,
    AnomalyExplanationResult,
    BehaviorResult,
    EvidenceEnvelope,
    EvidenceType,
    GraphEdge,
    GraphEvidenceResult,
    GraphNeighborhoodResult,
    ObservedActivity,
    RiskBreakdown,
    RiskComponent,
    TransactionPage,
    TransactionRecord,
    TypologyResult,
)
from src.observability.metrics import METRICS, attrs

WINDOW_DAYS = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}


class RiskArgs(BaseModel):
    alert_id: str = Field(min_length=1, max_length=128)


class BehaviorArgs(BaseModel):
    account_key: str = Field(min_length=3, max_length=128)
    window: Literal["1d", "7d", "30d", "90d"] = "7d"


class TransactionArgs(BaseModel):
    account_key: str | None = Field(default=None, max_length=128)
    counterparty: str | None = Field(default=None, max_length=128)
    transaction_ids: list[str] = Field(default_factory=list, max_length=100)
    start_time: datetime | None = None
    end_time: datetime | None = None
    direction: Literal["in", "out"] | None = None
    limit: int = Field(default=50, ge=1, le=500)
    cursor: str | None = None


class GraphEvidenceArgs(BaseModel):
    alert_id: str = Field(min_length=1, max_length=128)
    pattern: str | None = Field(default=None, max_length=64)


class NeighborhoodArgs(BaseModel):
    account_key: str = Field(min_length=3, max_length=128)
    hops: int = Field(default=1, ge=1, le=4)
    time_window: Literal["1d", "7d", "30d", "90d"] = "7d"


class TypologyArgs(BaseModel):
    pattern: str | None = Field(default=None, max_length=64)
    typology_code: str | None = Field(default=None, pattern=r"^T(0[1-9]|10)$")


class AnomalyArgs(BaseModel):
    alert_id: str = Field(min_length=1, max_length=128)
    account_key: str = Field(min_length=3, max_length=128)
    window: Literal["1d", "7d", "30d", "90d"] = "7d"


@dataclass
class ToolExecution:
    result: dict[str, Any]
    evidence: EvidenceEnvelope | None
    status: Literal["SUCCEEDED", "PARTIAL"] = "SUCCEEDED"


def _percentile(values: list[float], value: float) -> float:
    if not values:
        return 50.0
    below = sum(v < value for v in values)
    equal = sum(v == value for v in values)
    return round(100 * (below + 0.5 * equal) / len(values), 2)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def _observed_from_rows(
    account_key: str,
    rows: list[dict[str, Any]],
    history: list[dict[str, Any]],
    *,
    window_start: datetime,
    window_end: datetime,
    window_days: int,
) -> ObservedActivity:
    """Same window as the feature vector, kept in original units."""
    events: list[tuple[datetime, str, str, float]] = []
    for row in rows:
        direction = "out" if row["from_account_key"] == account_key else "in"
        counterparty = row["to_account_key"] if direction == "out" else row["from_account_key"]
        events.append((row["occurred_at"], direction, counterparty, float(row["amount"])))
    events.sort()
    incoming = [event for event in events if event[1] == "in"]
    outgoing = [event for event in events if event[1] == "out"]
    total_out = sum(event[3] for event in outgoing)

    rapid_amount = 0.0
    prior_incoming: datetime | None = None
    for timestamp, direction, _counterparty, amount in events:
        if direction == "in":
            prior_incoming = timestamp
        elif prior_incoming and timestamp - prior_incoming <= timedelta(hours=2):
            rapid_amount += amount

    dwell_hours: list[float] = []
    outgoing_times = [event[0] for event in outgoing]
    for incoming_time, *_ in incoming:
        next_out = next((out_time for out_time in outgoing_times if out_time >= incoming_time), None)
        if next_out:
            dwell_hours.append((next_out - incoming_time).total_seconds() / 3600)

    historical_counterparties: set[str] = set()
    for row in history:
        if row["from_account_key"] == account_key:
            historical_counterparties.add(row["to_account_key"])
        else:
            historical_counterparties.add(row["from_account_key"])
    current_counterparties = {event[2] for event in events}

    currencies = {row["currency"] for row in rows if row.get("currency")}
    return ObservedActivity(
        window_start=window_start,
        window_end=window_end,
        window_days=window_days,
        currency=currencies.pop() if len(currencies) == 1 else None,
        inflow_amount=round(sum(event[3] for event in incoming), 2),
        outflow_amount=round(total_out, 2),
        largest_amount=round(max((event[3] for event in events), default=0.0), 2),
        incoming_count=len(incoming),
        outgoing_count=len(outgoing),
        unique_in_counterparties=len({event[2] for event in incoming}),
        unique_out_counterparties=len({event[2] for event in outgoing}),
        new_counterparties=len(current_counterparties - historical_counterparties),
        rapid_outflow_amount=round(rapid_amount, 2),
        rapid_outflow_percent=round(100 * rapid_amount / total_out, 2) if total_out > 0 else 0.0,
        median_dwell_hours=round(statistics.median(dwell_hours), 2) if dwell_hours else None,
        active_days=len({event[0].date() for event in events}),
    )


def _behavior_from_rows(
    account_key: str, rows: list[dict[str, Any]], history: list[dict[str, Any]]
) -> dict[str, float | int]:
    events: list[tuple[datetime, str, str, float]] = []
    for row in rows:
        direction = "out" if row["from_account_key"] == account_key else "in"
        counterparty = row["to_account_key"] if direction == "out" else row["from_account_key"]
        events.append((row["occurred_at"], direction, counterparty, float(row["amount"])))
    events.sort()
    incoming = [event for event in events if event[1] == "in"]
    outgoing = [event for event in events if event[1] == "out"]
    amounts = [event[3] for event in events]
    total_in = sum(event[3] for event in incoming)
    total_out = sum(event[3] for event in outgoing)
    active_days = len({event[0].date() for event in events})

    rapid_amount = 0.0
    prior_incoming: datetime | None = None
    for timestamp, direction, _counterparty, amount in events:
        if direction == "in":
            prior_incoming = timestamp
        elif prior_incoming and timestamp - prior_incoming <= timedelta(hours=2):
            rapid_amount += amount

    dwell_hours: list[float] = []
    outgoing_times = [event[0] for event in outgoing]
    for incoming_time, *_ in incoming:
        next_out = next((out_time for out_time in outgoing_times if out_time >= incoming_time), None)
        if next_out:
            dwell_hours.append((next_out - incoming_time).total_seconds() / 3600)

    historical_counterparties: set[str] = set()
    for row in history:
        if row["from_account_key"] == account_key:
            historical_counterparties.add(row["to_account_key"])
        else:
            historical_counterparties.add(row["from_account_key"])
    current_counterparties = {event[2] for event in events}
    new_ratio = (
        len(current_counterparties - historical_counterparties) / len(current_counterparties)
        if current_counterparties
        else 0.0
    )

    repeated = sum(amounts.count(value) >= 2 for value in amounts) / len(amounts) if amounts else 0.0
    gaps = [(events[i][0] - events[i - 1][0]).total_seconds() / 60 for i in range(1, len(events))]
    std = statistics.stdev(amounts) if len(amounts) > 1 else 0.0
    return {
        "txn_count": len(events),
        "incoming_count": len(incoming),
        "outgoing_count": len(outgoing),
        "active_days": active_days,
        "txn_per_active_day": round(len(events) / max(active_days, 1), 6),
        "total_inflow": round(math.log1p(total_in), 6),
        "total_outflow": round(math.log1p(total_out), 6),
        "net_flow": round(math.copysign(math.log1p(abs(total_in - total_out)), total_in - total_out), 6),
        "outflow_inflow_ratio": round(total_out / max(total_in, 1e-6), 6),
        "rapid_outflow_ratio": round(rapid_amount / max(total_out, 1e-6), 6),
        "median_dwell_time": round(statistics.median(dwell_hours), 6) if dwell_hours else 999.0,
        "unique_in_counterparties": len({event[2] for event in incoming}),
        "unique_out_counterparties": len({event[2] for event in outgoing}),
        "new_counterparty_ratio": round(new_ratio, 6),
        "median_amount": round(math.log1p(statistics.median(amounts)), 6) if amounts else 0.0,
        "p90_amount": round(math.log1p(_quantile(amounts, 0.9)), 6) if amounts else 0.0,
        "amount_std": round(math.log1p(std), 6),
        "repeated_amount_ratio": round(repeated, 6),
        "median_inter_txn_gap": round(statistics.median(gaps), 6) if gaps else 99999.0,
        "p10_inter_txn_gap": round(_quantile(gaps, 0.1), 6) if gaps else 99999.0,
    }


class InvestigationTools:
    """Allow-listed deterministic tool gateway.

    All traversal and calculations happen here. Agent outputs can select a
    tool and bounded arguments, but cannot issue SQL or execute arbitrary code.
    """

    ALLOWED = {
        "GetRiskBreakdown",
        "GetAccountBehavior",
        "GetTransactions",
        "GetGraphEvidence",
        "GetGraphNeighborhood",
        "GetTypology",
        "GetAnomalyExplanation",
    }
    ARGUMENT_MODELS: dict[str, type[BaseModel]] = {
        "GetRiskBreakdown": RiskArgs,
        "GetAccountBehavior": BehaviorArgs,
        "GetTransactions": TransactionArgs,
        "GetGraphEvidence": GraphEvidenceArgs,
        "GetGraphNeighborhood": NeighborhoodArgs,
        "GetTypology": TypologyArgs,
        "GetAnomalyExplanation": AnomalyArgs,
    }
    DESCRIPTIONS = {
        "GetRiskBreakdown": "Retrieve the authoritative detector risk score and available branch contributions.",
        "GetAccountBehavior": "Retrieve deterministic account behavior features for a bounded time window.",
        "GetTransactions": "Retrieve bounded source transactions involving the investigation account.",
        "GetGraphEvidence": "Retrieve structured evidence emitted by the graph detector for this alert.",
        "GetGraphNeighborhood": "Traverse a bounded transaction neighborhood deterministically.",
        "GetTypology": "Resolve a typology through the versioned structured catalog.",
        "GetAnomalyExplanation": "Retrieve deterministic feature-deviation attribution for an ML alert.",
    }

    def __init__(self, session: Session, repository: InvestigationRepository, investigation_id: str):
        self.session = session
        self.repository = repository
        self.investigation_id = investigation_id
        self.state = repository.get(investigation_id)
        self.settings = get_settings()

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolExecution:
        if tool_name not in self.ALLOWED:
            self._reject_tool(tool_name, "Tool name is outside the allow-listed registry")
            raise ValueError(f"Công cụ {tool_name!r} không nằm trong danh sách được phép")
        try:
            validated = self.ARGUMENT_MODELS[tool_name].model_validate(self._bind_identity(tool_name, arguments))
            self._authorize(tool_name, validated)
        except Exception as exc:
            self._reject_tool(tool_name, type(exc).__name__)
            raise
        methods = {
            "GetRiskBreakdown": self.get_risk_breakdown,
            "GetAccountBehavior": self.get_account_behavior,
            "GetTransactions": self.get_transactions,
            "GetGraphEvidence": self.get_graph_evidence,
            "GetGraphNeighborhood": self.get_graph_neighborhood,
            "GetTypology": self.get_typology,
            "GetAnomalyExplanation": self.get_anomaly_explanation,
        }
        return methods[tool_name](validated.model_dump(mode="json", exclude_none=True))

    @classmethod
    def tool_catalog(cls) -> list[dict[str, Any]]:
        """Gemini-visible JSON schemas; execution remains backend-controlled."""
        return [
            {
                "name": name,
                "description": cls.DESCRIPTIONS[name],
                "parameters": cls.ARGUMENT_MODELS[name].model_json_schema(),
            }
            for name in sorted(cls.ALLOWED)
        ]

    def _reject_tool(self, tool_name: str, reason: str) -> None:
        event_type = "unauthorized_tool_request" if reason == "PermissionError" else "invalid_tool_request"
        METRICS.security_events.add(1, attrs(type=event_type))
        self.repository.add_trace(
            self.investigation_id,
            agent="investigation_supervisor",
            event_type="INVALID_TOOL_REQUEST",
            tool=tool_name[:128],
            rationale=f"Rejected Gemini tool request: {reason}.",
        )

    def _bind_identity(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Supply the subject the investigation is already pinned to.

        A model that asks for the right tool but forgets ``alert_id`` used to
        lose the whole call to a ValidationError. Filling these two fields in
        cannot widen access: ``_authorize`` rejects any value other than this
        investigation's own, so the only reachable value is the one bound here.
        Keys the tool does not declare are dropped rather than rejected.
        """
        fields = self.ARGUMENT_MODELS[tool_name].model_fields
        bound = {key: value for key, value in arguments.items() if key in fields}
        if "alert_id" in fields and not bound.get("alert_id"):
            bound["alert_id"] = self.state.alert_id
        if "account_key" in fields and not bound.get("account_key"):
            bound["account_key"] = self.state.account_key
        return bound

    def _authorize(self, tool_name: str, arguments: BaseModel) -> None:
        """Confine model-proposed arguments to the current investigation."""
        values = arguments.model_dump()
        if "alert_id" in values and values["alert_id"] != self.state.alert_id:
            raise PermissionError("Tool alert_id is outside the current investigation")
        if (
            tool_name
            in {
                "GetAccountBehavior",
                "GetTransactions",
                "GetGraphNeighborhood",
                "GetAnomalyExplanation",
            }
            and values.get("account_key") != self.state.account_key
        ):
            raise PermissionError("Tool account_key is outside the current investigation")

    def get_risk_breakdown(self, raw: dict[str, Any]) -> ToolExecution:
        args = RiskArgs.model_validate(raw)
        row = (
            self.session.execute(
                text("SELECT alert_id, account_key, detector, risk_score FROM alert WHERE alert_id = :id"),
                {"id": args.alert_id},
            )
            .mappings()
            .first()
        )
        if not row:
            raise LookupError(f"Không tìm thấy cảnh báo {args.alert_id}")
        score = round(float(row["risk_score"]) / 100, 6)
        source = {"rule": "rule", "ml": "anomaly", "graph": "graph"}[row["detector"]]
        components = {
            name: RiskComponent(
                score=score if name == source else 0,
                weight=1 if name == source else 0,
                contribution=score if name == source else 0,
                available=name == source,
                source_ref=f"alert:{args.alert_id}" if name == source else None,
            )
            for name in ("rule", "anomaly", "graph")
        }
        result = RiskBreakdown(
            alert_id=args.alert_id,
            final_risk_score=score,
            fusion_available=False,
            components=components,
            limitation=(
                "This repository does not yet have a score-fusion runtime; the alert detector score is the "
                "authoritative final score for this alert. Other branches are unavailable, not inferred."
            ),
        )
        evidence = self.repository.add_evidence(
            self.investigation_id,
            evidence_type=EvidenceType.RISK_BREAKDOWN,
            source="detection_engine",
            account_key=row["account_key"],
            payload=result.model_dump(mode="json"),
            source_record_ids=[args.alert_id],
        )
        if row["detector"] == "rule":
            reasons = [
                dict(reason)
                for reason in self.session.execute(
                    text(
                        """SELECT factor_code, factor_label, contribution, weight
                             FROM alert_reason WHERE alert_id = :id ORDER BY contribution DESC"""
                    ),
                    {"id": args.alert_id},
                ).mappings()
            ]
            self.repository.add_evidence(
                self.investigation_id,
                evidence_type=EvidenceType.RULE_TRIGGER,
                source="rule_engine",
                account_key=row["account_key"],
                payload={"alert_id": args.alert_id, "triggered_rules": reasons},
                source_record_ids=[args.alert_id, *[reason["factor_code"] for reason in reasons]],
            )
        return ToolExecution(result=result.model_dump(mode="json"), evidence=evidence)

    def _behavior(self, account_key: str, window: str) -> BehaviorResult:
        if not self.session.execute(
            text("SELECT EXISTS(SELECT 1 FROM account WHERE account_key = :account)"), {"account": account_key}
        ).scalar_one():
            raise LookupError(f"Không tìm thấy tài khoản {account_key}")
        as_of = self.state.snapshot_time
        start = as_of - timedelta(days=WINDOW_DAYS[window])
        rows = [
            dict(row)
            for row in self.session.execute(
                text(
                    """SELECT transaction_id, occurred_at, from_account_key, to_account_key,
                              amount, currency
                         FROM transaction
                        WHERE occurred_at > :start AND occurred_at <= :as_of
                          AND (from_account_key = :account OR to_account_key = :account)
                        ORDER BY occurred_at, transaction_id"""
                ),
                {"start": start, "as_of": as_of, "account": account_key},
            ).mappings()
        ]
        history = [
            dict(row)
            for row in self.session.execute(
                text(
                    """SELECT occurred_at, from_account_key, to_account_key, amount
                         FROM transaction
                        WHERE occurred_at <= :start
                          AND (from_account_key = :account OR to_account_key = :account)"""
                ),
                {"start": start, "account": account_key},
            ).mappings()
        ]
        return BehaviorResult(
            account_key=account_key,
            window=window,
            as_of_time=as_of,
            feature_definition_version="feature_spec_v1",
            features=_behavior_from_rows(account_key, rows, history),
            observed=_observed_from_rows(
                account_key, rows, history, window_start=start, window_end=as_of, window_days=WINDOW_DAYS[window]
            ),
        )

    def get_account_behavior(self, raw: dict[str, Any]) -> ToolExecution:
        args = BehaviorArgs.model_validate(raw)
        result = self._behavior(args.account_key, args.window)
        source_ref = f"features:{args.account_key}:{result.as_of_time.isoformat()}:{args.window}:feature_spec_v1"
        evidence = self.repository.add_evidence(
            self.investigation_id,
            evidence_type=EvidenceType.BEHAVIOR_FEATURE,
            source="feature_service",
            account_key=args.account_key,
            payload=result.model_dump(mode="json"),
            source_record_ids=[source_ref],
        )
        return ToolExecution(result=result.model_dump(mode="json"), evidence=evidence)

    def get_transactions(self, raw: dict[str, Any]) -> ToolExecution:
        args = TransactionArgs.model_validate(raw)
        if not args.account_key and not args.transaction_ids:
            raise ValueError("GetTransactions yêu cầu account_key hoặc transaction_ids")
        limit = min(args.limit, self.settings.investigation_tx_limit)
        offset = int(args.cursor or "0")
        if offset < 0 or offset > 10_000:
            raise ValueError("Con trỏ phân trang giao dịch không hợp lệ")
        conditions = ["occurred_at <= :snapshot"]
        params: dict[str, Any] = {"snapshot": self.state.snapshot_time, "limit": limit + 1, "offset": offset}
        if args.transaction_ids:
            ids = [int(value) for value in args.transaction_ids]
            conditions.append("transaction_id = ANY(:transaction_ids)")
            params["transaction_ids"] = ids
        if args.account_key:
            if args.direction == "in":
                conditions.append("to_account_key = :account")
            elif args.direction == "out":
                conditions.append("from_account_key = :account")
            else:
                conditions.append("(from_account_key = :account OR to_account_key = :account)")
            params["account"] = args.account_key
        if args.counterparty:
            conditions.append("(from_account_key = :counterparty OR to_account_key = :counterparty)")
            params["counterparty"] = args.counterparty
        if args.start_time:
            conditions.append("occurred_at >= :start_time")
            params["start_time"] = args.start_time
        if args.end_time:
            conditions.append("occurred_at <= :end_time")
            params["end_time"] = args.end_time
        rows = list(
            self.session.execute(
                text(
                    f"""SELECT transaction_id, occurred_at, from_account_key, to_account_key,
                               amount, currency, channel
                          FROM transaction WHERE {" AND ".join(conditions)}
                         ORDER BY occurred_at DESC, transaction_id DESC
                         LIMIT :limit OFFSET :offset"""
                ),
                params,
            ).mappings()
        )
        truncated = len(rows) > limit
        rows = rows[:limit]
        records = [
            TransactionRecord(
                transaction_id=str(row["transaction_id"]),
                source=row["from_account_key"],
                destination=row["to_account_key"],
                timestamp=row["occurred_at"],
                amount=float(row["amount"]),
                currency=row["currency"],
                payment_format=row["channel"],
            )
            for row in rows
        ]
        page = TransactionPage(
            items=records,
            limit=limit,
            next_cursor=str(offset + limit) if truncated else None,
            truncated=truncated,
        )
        refs = [record.transaction_id for record in records]
        evidence = self.repository.add_evidence(
            self.investigation_id,
            evidence_type=EvidenceType.TRANSACTION,
            source="transaction_service",
            account_key=args.account_key or self.state.account_key,
            payload=page.model_dump(mode="json"),
            source_record_ids=refs or ["empty-query-result"],
            transaction_refs=refs,
            untrusted=True,
        )
        return ToolExecution(result=page.model_dump(mode="json"), evidence=evidence)

    def get_graph_evidence(self, raw: dict[str, Any]) -> ToolExecution:
        args = GraphEvidenceArgs.model_validate(raw)
        rows = list(
            self.session.execute(
                text(
                    """SELECT evidence_id, payload FROM evidence
                        WHERE case_id = :case_id AND source_table = 'graph_detector'
                        ORDER BY retrieved_at DESC"""
                ),
                {"case_id": self.state.case_id},
            ).mappings()
        )
        for row in rows:
            payload = row["payload"]
            if payload.get("pattern") and (not args.pattern or payload["pattern"] == args.pattern):
                result = GraphEvidenceResult(**payload, evidence_id=row["evidence_id"], available=True)
                transaction_refs = [edge.transaction_id for edge in result.edges]
                evidence = self.repository.add_evidence(
                    self.investigation_id,
                    evidence_type=EvidenceType.GRAPH_PATTERN,
                    source="graph_detector",
                    account_key=self.state.account_key,
                    payload=result.model_dump(mode="json", by_alias=True),
                    source_record_ids=[row["evidence_id"], *transaction_refs],
                    transaction_refs=transaction_refs,
                )
                return ToolExecution(result=result.model_dump(mode="json", by_alias=True), evidence=evidence)
        result = GraphEvidenceResult(
            available=False,
            missing_reason="No structured graph-detector evidence exists for this alert; no graph pattern may be claimed.",
        )
        return ToolExecution(result=result.model_dump(mode="json"), evidence=None, status="PARTIAL")

    def get_graph_neighborhood(self, raw: dict[str, Any]) -> ToolExecution:
        args = NeighborhoodArgs.model_validate(raw)
        hops = min(args.hops, self.settings.max_graph_hops)
        start = self.state.snapshot_time - timedelta(days=WINDOW_DAYS[args.time_window])
        visited = {args.account_key}
        frontier = {args.account_key}
        edge_rows: dict[str, dict[str, Any]] = {}
        truncated = False
        for _ in range(hops):
            if not frontier:
                break
            rows = self.session.execute(
                text(
                    """SELECT transaction_id, from_account_key, to_account_key
                         FROM transaction
                        WHERE occurred_at > :start AND occurred_at <= :snapshot
                          AND (from_account_key = ANY(:frontier) OR to_account_key = ANY(:frontier))
                        ORDER BY occurred_at DESC, transaction_id DESC
                        LIMIT :edge_limit"""
                ),
                {
                    "start": start,
                    "snapshot": self.state.snapshot_time,
                    "frontier": list(frontier),
                    "edge_limit": self.settings.max_graph_edges + 1,
                },
            ).mappings()
            next_frontier: set[str] = set()
            for row in rows:
                if len(edge_rows) >= self.settings.max_graph_edges:
                    truncated = True
                    break
                edge_rows[str(row["transaction_id"])] = dict(row)
                for account in (row["from_account_key"], row["to_account_key"]):
                    if account not in visited:
                        if len(visited) >= self.settings.max_graph_nodes:
                            truncated = True
                            continue
                        visited.add(account)
                        next_frontier.add(account)
            frontier = next_frontier
        edges = [
            GraphEdge.model_validate(
                {"from": row["from_account_key"], "to": row["to_account_key"], "transaction_id": tx_id}
            )
            for tx_id, row in edge_rows.items()
        ]
        result = GraphNeighborhoodResult(
            account_key=args.account_key,
            hops=hops,
            nodes=sorted(visited),
            edges=edges,
            truncated=truncated,
        )
        evidence = self.repository.add_evidence(
            self.investigation_id,
            evidence_type=EvidenceType.GRAPH_NEIGHBORHOOD,
            source="transaction_graph_service",
            account_key=args.account_key,
            payload=result.model_dump(mode="json", by_alias=True),
            source_record_ids=list(edge_rows) or [f"empty-neighborhood:{args.account_key}"],
            transaction_refs=list(edge_rows),
        )
        return ToolExecution(result=result.model_dump(mode="json", by_alias=True), evidence=evidence)

    @staticmethod
    def _catalog() -> list[dict[str, Any]]:
        path = Path(__file__).with_name("typologies.json")
        return json.loads(path.read_text(encoding="utf-8"))

    def get_typology(self, raw: dict[str, Any]) -> ToolExecution:
        args = TypologyArgs.model_validate(raw)
        if not args.pattern and not args.typology_code:
            raise ValueError("GetTypology yêu cầu pattern hoặc typology_code")
        entry = next(
            (
                item
                for item in self._catalog()
                if (args.pattern and item["pattern"] == args.pattern)
                or (args.typology_code and item["typology_code"] == args.typology_code)
            ),
            None,
        )
        if not entry:
            raise LookupError("Không tìm thấy ánh xạ nhóm hành vi")
        result = TypologyResult(**entry)
        evidence = self.repository.add_evidence(
            self.investigation_id,
            evidence_type=EvidenceType.TYPOLOGY_MAPPING,
            source="typology_registry",
            account_key=self.state.account_key,
            payload=result.model_dump(mode="json"),
            source_record_ids=[f"{result.typology_code}:{result.version}"],
        )
        return ToolExecution(result=result.model_dump(mode="json"), evidence=evidence)

    def get_anomaly_explanation(self, raw: dict[str, Any]) -> ToolExecution:
        args = AnomalyArgs.model_validate(raw)
        alert = (
            self.session.execute(
                text(
                    """SELECT alert_id, risk_score FROM alert
                        WHERE account_key = :account AND detector = 'ml'
                          AND (alert_id = :alert_id OR case_id = :case_id)
                        ORDER BY (alert_id = :alert_id) DESC, created_at DESC LIMIT 1"""
                ),
                {"account": args.account_key, "alert_id": args.alert_id, "case_id": self.state.case_id},
            )
            .mappings()
            .first()
        )
        if not alert:
            result = AnomalyExplanationResult(
                account_key=args.account_key,
                anomaly_score=0,
                top_anomalous_features=[],
                method="unavailable",
                available=False,
                missing_reason="No Isolation Forest detector result exists for this alert/account.",
            )
            return ToolExecution(result=result.model_dump(mode="json"), evidence=None, status="PARTIAL")

        target = self._behavior(args.account_key, args.window)
        reason_codes = {
            str(code).lower()
            for code in self.session.execute(
                text("SELECT factor_code FROM alert_reason WHERE alert_id = :id"), {"id": alert["alert_id"]}
            ).scalars()
        }
        candidate_features = [name for name in target.features if name.lower() in reason_codes]
        if not candidate_features:
            candidate_features = list(target.features)

        # Deterministic reference distribution from accounts active in the
        # same point-in-time window. This explains deviations; it does not
        # alter or approximate the detector score.
        active_accounts = list(
            self.session.execute(
                text(
                    """SELECT DISTINCT account_key FROM (
                           SELECT from_account_key AS account_key FROM transaction
                            WHERE occurred_at > :start AND occurred_at <= :snapshot
                           UNION
                           SELECT to_account_key AS account_key FROM transaction
                            WHERE occurred_at > :start AND occurred_at <= :snapshot
                       ) active ORDER BY account_key LIMIT 500"""
                ),
                {
                    "start": self.state.snapshot_time - timedelta(days=WINDOW_DAYS[args.window]),
                    "snapshot": self.state.snapshot_time,
                },
            ).scalars()
        )
        reference: dict[str, list[float]] = defaultdict(list)
        for account in active_accounts:
            behavior = self._behavior(account, args.window)
            for feature in candidate_features:
                reference[feature].append(float(behavior.features[feature]))
        ranked: list[AnomalousFeature] = []
        for feature in candidate_features:
            value = float(target.features[feature])
            percentile = _percentile(reference[feature], value)
            ranked.append(
                AnomalousFeature(
                    feature=feature,
                    value=value,
                    reference_percentile=percentile,
                    source_ref=f"feature:{args.account_key}:{feature}:{target.as_of_time.isoformat()}",
                )
            )
        ranked.sort(key=lambda item: abs(item.reference_percentile - 50), reverse=True)
        result = AnomalyExplanationResult(
            account_key=args.account_key,
            anomaly_score=round(float(alert["risk_score"]) / 100, 6),
            top_anomalous_features=ranked[:5],
            method="same-window empirical percentile; detector score unchanged",
            available=True,
        )
        evidence = self.repository.add_evidence(
            self.investigation_id,
            evidence_type=EvidenceType.ANOMALY_EXPLANATION,
            source="anomaly_explanation_service",
            account_key=args.account_key,
            payload=result.model_dump(mode="json"),
            source_record_ids=[alert["alert_id"], f"feature_spec_v1:{args.window}"],
        )
        return ToolExecution(result=result.model_dump(mode="json"), evidence=evidence)


def timed_execute(
    tools: InvestigationTools, tool_name: str, arguments: dict[str, Any]
) -> tuple[ToolExecution, datetime, int]:
    started_at = datetime.now(UTC)
    started = time.monotonic()
    result = tools.execute(tool_name, arguments)
    return result, started_at, round((time.monotonic() - started) * 1000)
