#!/usr/bin/env python3
"""Sinh một case ABM "Thành phố tài chính Việt Nam" và nạp vào cơ sở dữ liệu.

Nguồn thiết kế: ABM_Thanh_pho_tai_chinh_Viet_Nam_AI_Agent_AML_BAN_CUOI_v2.0.pdf.
Bản này hiện thực **kịch bản VN-CA-03** (đánh bạc trực tuyến kết hợp rửa tiền),
là kịch bản mà tài liệu gọi là "điểm thiết kế quan trọng nhất cần sửa" ở
chương 10.3, vì nó buộc phải tách hai lớp dữ liệu:

  * Thế giới ẩn có operator, người chơi, đại lý và **ledger cược**. Ledger đó
    tồn tại thật (trên server đối tượng) nhưng ngân hàng không nhìn thấy trước
    khi điều tra. Nó vào `fc_gt.hidden_gambling_ledger` và không bao giờ được
    dùng làm đặc trưng.
  * Bằng chứng ngân hàng quan sát được — nhiều người nạp vào một cụm tài khoản,
    fan-in/fan-out, dùng chung thiết bị, đổi sang USDT — vào schema `fc`. Đây
    là toàn bộ những gì detector được phép học.

Nhờ tách như vậy, số đo "phát hiện sớm bao nhiêu" mới có nghĩa: nó là khoảng
cách giữa `first_illicit_event_time` (thế giới ẩn biết) và tín hiệu đầu tiên
quan sát được theo từng vai trò.

Quy mô cố ý nhỏ — đây là một case để chạy thử đường ống, không phải bộ dữ liệu
huấn luyện. Xem `--scale` nếu muốn sinh dày hơn.

Cách dùng:
    python scripts/abm_generate.py                 # sinh và nạp
    python scripts/abm_generate.py --dry-run       # in thống kê, không ghi
    python scripts/abm_generate.py --force         # xoá lần chạy cũ cùng ID rồi nạp lại
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.db.session import get_session  # noqa: E402

log = logging.getLogger("abm")

# ---------------------------------------------------------------------
# Hằng số của lần chạy. Ba giá trị này cùng với seed xác định toàn bộ đầu ra;
# đổi bất kỳ cái nào cũng phải tăng version để dữ liệu cũ vẫn truy nguyên được.
# ---------------------------------------------------------------------

SIMULATION_ID = "SIM-VNCA03-001"
SCENARIO = "VN-CA-03"
GENERATOR_VERSION = "abm-generate/1.0"
SCHEMA_VERSION = "fc-1.0"
PARAMETER_SET_ID = "PS-VNCA03-2026-08"
CASE_ID = "CASE-2026-0341"
NETWORK_ID = "NET-GMB-01"
DEFAULT_SEED = 20260804

# Thế giới mô phỏng kéo dài 45 ngày và kết thúc ở "bây giờ" — để mọi màn hình
# có dữ liệu trong mọi cửa sổ thời gian (1h → 30d).
WORLD_DAYS = 45

# Vai trò mà một tổ chức tài chính thực sự quan sát được. Bằng chứng ngoài hai
# vai trò này thuộc tầng điều tra và không được vào hồ sơ vụ việc của ngân hàng.
BANK_VISIBLE_ROLES = frozenset({"BANK", "PUBLIC"})


# ---------------------------------------------------------------------
# Source registry — chương 13.1
#
# Mỗi tham số phải trỏ về một nguồn. Ở đây phần lớn là `expert_assumption` với
# độ tin cậy thấp và điều cấm ghi rõ: dữ liệu tổng hợp không được dùng để suy
# ra tỷ lệ thật của Việt Nam. Đó chính là điều tài liệu cảnh báo ở chương 13.2.
# ---------------------------------------------------------------------

SOURCES: list[dict[str, Any]] = [
    {
        "source_id": "VN_LEGAL_PCRT_2022",
        "source_type": "legal_text",
        "scope": "Nghĩa vụ báo cáo giao dịch đáng ngờ và giao dịch giá trị lớn",
        "period": "2022-2026",
        "jurisdiction": "Việt Nam",
        "fields_supported": "Ngưỡng báo cáo, loại giao dịch phải báo cáo; không hỗ trợ base rate",
        "transformation": "manual mapping",
        "confidence": 0.95,
        "rationale": "Văn bản pháp luật hiện hành, trích dẫn trực tiếp.",
        "access_level": "public",
        "owner": "Nhóm tuân thủ FIN-07",
        "reviewer": "AML SME",
        "valid_from": "2023-03-01",
        "valid_to": None,
        "prohibited_uses": "Không dùng để suy ra ngưỡng kiểm soát nội bộ thật của bất kỳ tổ chức nào.",
    },
    {
        "source_id": "VN_TYPOLOGY_GAMBLING_MULE_USDT",
        "source_type": "official_case",
        "scope": "Cấu trúc tài khoản nhiều tầng và chuyển đổi USDT trong các vụ đánh bạc trực tuyến",
        "period": "2025-2026",
        "jurisdiction": "Việt Nam",
        "fields_supported": "Số tầng tài khoản, hình thái fan-in/fan-out, kênh chuyển đổi; không hỗ trợ base rate",
        "transformation": "typology extraction",
        "confidence": 0.70,
        "rationale": (
            "Rút từ mô tả công khai của các vụ án đã khởi tố. Đủ để dựng hình thái, không đủ để ước lượng tần suất."
        ),
        "access_level": "public",
        "owner": "Nhóm AML FIN-07",
        "reviewer": "AML SME",
        "valid_from": "2026-01-01",
        "valid_to": None,
        "prohibited_uses": (
            "Không dùng để suy ra tỷ lệ rửa tiền toàn quốc, không dùng để tái nhận dạng "
            "cá nhân hay tổ chức trong các vụ án nguồn."
        ),
    },
    {
        "source_id": "PUBLIC_CHAIN_TRC20_USDT",
        "source_type": "public_blockchain",
        "scope": "Hình thái chuyển USDT trên TRC20: kích thước giao dịch, độ trễ giữa các hop",
        "period": "2025-2026",
        "jurisdiction": "Toàn cầu",
        "fields_supported": "Phân phối số tiền, khoảng thời gian giữa các hop, số hop trước off-ramp",
        "transformation": "distribution fit",
        "confidence": 0.80,
        "rationale": "Dữ liệu on-chain công khai, kiểm chứng lại được.",
        "access_level": "public",
        "owner": "Nhóm dữ liệu FIN-07",
        "reviewer": "Graph/ML lead",
        "valid_from": "2025-06-01",
        "valid_to": None,
        "prohibited_uses": "Không gán nhãn dịch vụ cho địa chỉ thật; mọi địa chỉ trong dataset là tổng hợp.",
    },
    {
        "source_id": "EXPERT_DEVICE_SHARING_VN",
        "source_type": "expert_assumption",
        "scope": "Tỷ lệ dùng chung thiết bị/IP trong cụm tài khoản được thuê hoặc mua lại",
        "period": "2026",
        "jurisdiction": "Việt Nam",
        "fields_supported": "Số tài khoản trên mỗi thiết bị, độ tin cậy của bằng chứng IP",
        "transformation": "manual mapping",
        "confidence": 0.45,
        "rationale": (
            "Ý kiến chuyên gia có khoảng nhạy cảm rộng. NAT của nhà mạng khiến bằng chứng "
            "cùng IP yếu hơn nhiều so với cùng IMEI."
        ),
        "access_level": "internal",
        "owner": "Nhóm AML FIN-07",
        "reviewer": "AML SME",
        "valid_from": "2026-01-01",
        "valid_to": "2027-01-01",
        "prohibited_uses": "Không dùng làm bằng chứng độc lập để kết luận quan hệ sở hữu.",
    },
]

# Trung tâm tài chính. `jurisdiction_risk` có `known_from` vì chương 10.2 yêu
# cầu nhãn rủi ro pháp lý phải version hoá, không gán cứng.
HUBS: list[dict[str, Any]] = [
    ("HUB-HAN", "Hà Nội", "VN", 21.028, 105.850, "medium"),
    ("HUB-SGN", "TP. Hồ Chí Minh", "VN", 10.780, 106.700, "medium"),
    ("HUB-DAD", "Đà Nẵng", "VN", 16.047, 108.206, "low"),
    ("HUB-PNH", "Phnom Penh", "KH", 11.562, 104.888, "high"),
    ("HUB-SIN", "Singapore", "SG", 1.352, 103.820, "low"),
    ("HUB-HKG", "Hong Kong", "HK", 22.320, 114.170, "medium"),
    ("HUB-BKK", "Bangkok", "TH", 13.750, 100.500, "medium"),
    ("HUB-DXB", "Dubai", "AE", 25.200, 55.300, "medium"),
]

BANKS = ["VCB", "TCB", "MB", "ACB", "VPB", "STB", "BIDV"]

VN_NAMES = [
    "Trần Văn Hòa",
    "Nguyễn Thị Mai",
    "Lê Quốc Bảo",
    "Phạm Minh Tuấn",
    "Đỗ Thu Hằng",
    "Vũ Đức Long",
    "Hoàng Anh Dũng",
    "Bùi Ngọc Lan",
    "Đặng Văn Khánh",
    "Ngô Thị Hương",
    "Phan Tấn Phát",
    "Lý Gia Hân",
]


@dataclass
class World:
    """Kết quả sinh, giữ trong bộ nhớ trước khi ghi xuống cơ sở dữ liệu."""

    entities: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    corridors: list[dict[str, Any]] = field(default_factory=list)
    crypto: list[dict[str, Any]] = field(default_factory=list)
    # Chiếu sang các bảng vận hành của console (schema public)
    customers: list[dict[str, Any]] = field(default_factory=list)
    accounts: list[dict[str, Any]] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    alert_reasons: list[dict[str, Any]] = field(default_factory=list)
    evidences: list[dict[str, Any]] = field(default_factory=list)
    case_row: dict[str, Any] = field(default_factory=dict)
    exposures: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    agent_runs: list[dict[str, Any]] = field(default_factory=list)
    agent_steps: list[dict[str, Any]] = field(default_factory=list)
    benchmarks: list[dict[str, Any]] = field(default_factory=list)
    monitors: list[dict[str, Any]] = field(default_factory=list)
    dq_checks: list[dict[str, Any]] = field(default_factory=list)
    projects: list[dict[str, Any]] = field(default_factory=list)
    # Thế giới ẩn
    gt_roles: list[dict[str, Any]] = field(default_factory=list)
    gt_signals: list[dict[str, Any]] = field(default_factory=list)
    gt_ledger: list[dict[str, Any]] = field(default_factory=list)
    gt_case: dict[str, Any] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        return {
            "entity": len(self.entities),
            "relationship": len(self.relationships),
            "corridor_flow": len(self.corridors),
            "crypto_transfer": len(self.crypto),
            "exposure_label": len(self.exposures),
            "observation_event": len(self.observations),
            "agent_run": len(self.agent_runs),
            "agent_step": len(self.agent_steps),
            "benchmark_result": len(self.benchmarks),
            "model_monitor": len(self.monitors),
            "data_quality_check": len(self.dq_checks),
            "token_project": len(self.projects),
            "gt_hidden_role": len(self.gt_roles),
            "gt_first_signal": len(self.gt_signals),
            "gt_gambling_ledger": len(self.gt_ledger),
            "→ customer": len(self.customers),
            "→ account": len(self.accounts),
            "→ transaction": len(self.transactions),
            "→ alert": len(self.alerts),
            "→ evidence": len(self.evidences),
        }


class Generator:
    """Sinh thế giới ẩn rồi chiếu nó thành bằng chứng quan sát được."""

    def __init__(self, seed: int, scale: int) -> None:
        self.rng = random.Random(seed)
        self.seed = seed
        self.scale = scale
        self.now = datetime.now(UTC).replace(microsecond=0)
        self.t0 = self.now - timedelta(days=WORLD_DAYS)
        self.w = World()

    # -- tiện ích thời gian ------------------------------------------

    def at(self, day: float) -> datetime:
        """Mốc thời gian ở ngày thứ `day` kể từ đầu thế giới mô phỏng."""
        return self.t0 + timedelta(days=day)

    def jitter(self, base: datetime, hours: float) -> datetime:
        return base + timedelta(hours=self.rng.uniform(-hours, hours))

    # -- thực thể -----------------------------------------------------

    def add_entity(
        self,
        entity_id: str,
        entity_type: str,
        label: str,
        *,
        subtitle: str = "",
        hub_id: str | None = None,
        risk: int = 0,
        first_day: float = 0,
        last_day: float | None = None,
        attributes: dict[str, Any] | None = None,
        hard_negative: bool = False,
        access_tier: str = "BANK",
    ) -> str:
        last = WORLD_DAYS if last_day is None else last_day
        self.w.entities.append(
            {
                "entity_id": entity_id,
                "simulation_id": SIMULATION_ID,
                "entity_type": entity_type,
                "label": label,
                "subtitle": subtitle,
                "hub_id": hub_id,
                "risk_score": max(0, min(100, risk)),
                "first_seen": self.at(first_day),
                "last_seen": self.at(last),
                "attributes": json.dumps(attributes or {}, ensure_ascii=False),
                "is_hard_negative": hard_negative,
                "access_tier": access_tier,
            }
        )
        return entity_id

    def add_rel(
        self,
        source: str,
        target: str,
        kind: str,
        *,
        label: str = "",
        amount: float | None = None,
        day: float = 0,
        inferred: bool = False,
        confidence: float | None = None,
        logic: str | None = None,
    ) -> None:
        rid = f"REL-{len(self.w.relationships) + 1:04d}"
        self.w.relationships.append(
            {
                "relationship_id": rid,
                "simulation_id": SIMULATION_ID,
                "source_id": source,
                "target_id": target,
                "kind": kind,
                "label": label,
                "amount_usd": amount,
                "is_inferred": inferred,
                "confidence": confidence,
                "inference_logic": logic,
                "known_from": self.at(day),
                "valid_to": None,
            }
        )

    def add_observation(
        self,
        evidence_id: str,
        role: str,
        day: float,
        acquisition: str,
        *,
        confidence: float,
        summary: str,
        legal_basis: str | None = None,
        visible: bool = True,
        redaction: str = "none",
        custody: str | None = None,
    ) -> None:
        self.w.observations.append(
            {
                "observation_event_id": f"OBS-{len(self.w.observations) + 1:04d}",
                "simulation_id": SIMULATION_ID,
                "evidence_item_id": evidence_id,
                "observer_role": role,
                "available_from": self.at(day),
                "acquisition_type": acquisition,
                "legal_basis_id": legal_basis,
                "redaction_profile": redaction,
                "source_confidence": confidence,
                "chain_of_custody_id": custody,
                "is_visible_to_model": visible,
                "summary": summary,
            }
        )

    # -- các lớp của kịch bản ----------------------------------------

    def build(self) -> World:
        self._build_hidden_operator()
        self._build_players()
        self._build_mules()
        self._build_devices()
        self._build_aggregators()
        self._build_p2p_and_crypto()
        self._build_hard_negatives()
        self._build_corridors()
        self._build_ground_truth()
        self._build_operational()
        self._build_agent_run()
        self._build_benchmarks()
        self._build_monitoring()
        self._build_data_quality()
        self._build_token_project()
        return self.w

    def _build_hidden_operator(self) -> None:
        """Nền tảng đánh bạc và hai trung gian thanh toán.

        Nền tảng đặt `access_tier='LAW_ENFORCEMENT'`: trước khi có điều tra,
        ngân hàng không biết cụm tài khoản này thuộc về một nền tảng cá cược.
        Đây đúng là điều chương 10.3 nhấn mạnh — detector ngân hàng phải phát
        hiện được mạng lưới thu hộ *trước khi* biết chắc đó là gambling.
        """
        self.add_entity(
            "PLAT-LS88",
            "platform",
            "LuckyStar88",
            subtitle="nền tảng cá cược ngoài lãnh thổ",
            hub_id="HUB-PNH",
            risk=96,
            first_day=0,
            attributes={"domain_age_days": 210, "hosting": "offshore"},
            access_tier="LAW_ENFORCEMENT",
        )
        for idx, (eid, name) in enumerate([("PSP-GATE", "PT-Gate"), ("PSP-FAST", "FastPay88")]):
            self.add_entity(
                eid,
                "platform",
                name,
                subtitle="trung gian thanh toán",
                hub_id="HUB-PNH",
                risk=74 - idx * 3,
                first_day=0.5 + idx,
                access_tier="LAW_ENFORCEMENT",
            )
            self.add_rel("PLAT-LS88", eid, "control", label="điều phối thanh toán", day=0.5 + idx)

    def _build_players(self) -> None:
        """Hai nhóm người chơi. Đây là nguồn tiền thật của mạng lưới."""
        for idx, (eid, label, count) in enumerate(
            [("POOL-A", "Nhóm người chơi A", 2100), ("POOL-B", "Nhóm người chơi B", 1400)]
        ):
            self.add_entity(
                eid,
                "person",
                label,
                subtitle=f"~{count:,} người chơi".replace(",", "."),
                hub_id="HUB-SGN" if idx == 0 else "HUB-HAN",
                risk=22 - idx * 2,
                first_day=idx * 0.5,
                attributes={"population": count},
                access_tier="LAW_ENFORCEMENT",
            )
            self.add_rel(
                eid, "PLAT-LS88", "transfer", label="nạp tiền", amount=4_100_000 - idx * 1_500_000, day=idx * 0.5
            )

    def _build_mules(self) -> None:
        """Cụm tài khoản trung gian — lớp bằng chứng chính mà ngân hàng thấy.

        Mở rải rác trong 30 ngày chứ không cùng lúc: mở đồng loạt là tín hiệu
        quá dễ, và các vụ thật cũng không như vậy.
        """
        self.mules: list[str] = []
        n = 8 + self.scale * 4
        for i in range(n):
            bank = BANKS[i % len(BANKS)]
            eid = f"ACC-MULE-{i + 1:02d}"
            day = 2 + i * (28 / max(1, n - 1))
            self.add_entity(
                eid,
                "account",
                f"Mule {i + 1:02d}",
                subtitle=f"{bank} •{self.rng.randint(1000, 9999)}",
                hub_id="HUB-SGN" if i % 3 else "HUB-HAN",
                risk=self.rng.randint(74, 89),
                first_day=day,
                attributes={"bank_code": bank, "account_age_days": round(WORLD_DAYS - day)},
            )
            self.mules.append(eid)
            src = "PSP-GATE" if i % 2 == 0 else "PSP-FAST"
            amount = round(self.rng.uniform(320_000, 1_200_000), 2)
            self.add_rel(src, eid, "transfer", label=f"${amount / 1e6:.2f}M", amount=amount, day=day + 1)

        # Chủ tài khoản. Một người đứng tên nhiều tài khoản là bằng chứng
        # quan sát trực tiếp từ hồ sơ KYC — không phải suy luận.
        self.owners: list[str] = []
        per_owner = 3
        for i in range(0, len(self.mules), per_owner):
            oid = f"PER-OWN-{i // per_owner + 1:02d}"
            self.add_entity(
                oid,
                "person",
                VN_NAMES[(i // per_owner) % len(VN_NAMES)],
                subtitle=f"chủ {per_owner} tài khoản",
                hub_id="HUB-SGN",
                risk=self.rng.randint(68, 80),
                first_day=2 + i,
            )
            self.owners.append(oid)
            for m in self.mules[i : i + per_owner]:
                self.add_rel(oid, m, "owns", label="đứng tên", day=2 + i)

        self.add_observation(
            "EV-201",
            "BANK",
            2,
            "native_system",
            confidence=0.98,
            summary="Hồ sơ mở tài khoản và KYC của cụm tài khoản trung gian — hệ thống ngân hàng có sẵn.",
        )

    def _build_devices(self) -> None:
        """Thiết bị và IP dùng chung.

        Chú ý mức độ tin cậy: cùng IMEI là bằng chứng mạnh, cùng IP thì yếu vì
        NAT của nhà mạng khiến hàng nghìn thuê bao chia sẻ một địa chỉ. Chênh
        lệch này được ghi thẳng vào `confidence` và `inference_logic` để analyst
        phản biện được, đúng yêu cầu của phụ lục E.
        """
        devices = [
            ("DEV-A", "Thiết bị A", "IMEI …8812", "imei", 0.86),
            ("DEV-B", "Thiết bị B", "IP 171.244.x.x", "ip", 0.68),
            ("DEV-C", "Thiết bị C", "IP 113.161.x.x", "ip", 0.71),
        ]
        for idx, (eid, label, sub, kind, base_conf) in enumerate(devices):
            self.add_entity(
                eid,
                "device",
                label,
                subtitle=sub,
                hub_id="HUB-SGN",
                risk=self.rng.randint(62, 72),
                first_day=2 + idx,
                attributes={"evidence_kind": kind},
            )
            for m in self.mules[idx :: len(devices)]:
                sessions = self.rng.randint(4, 41)
                conf = round(base_conf * min(1.0, 0.5 + sessions / 40), 2)
                logic = (
                    f"Cùng IMEI trong {sessions} phiên đăng nhập; khớp thêm fingerprint trình duyệt."
                    if kind == "imei"
                    else (
                        f"Cùng địa chỉ IP tĩnh trong {sessions} phiên. Không loại trừ được NAT "
                        f"của nhà mạng — bằng chứng này một mình không đủ để kết luận quan hệ."
                    )
                )
                self.add_rel(
                    eid,
                    m,
                    "device",
                    label="dùng chung thiết bị",
                    day=3 + idx,
                    inferred=True,
                    confidence=conf,
                    logic=logic,
                )

        self.add_observation(
            "EV-211",
            "BANK",
            3,
            "native_system",
            confidence=0.74,
            summary="Nhật ký phiên đăng nhập: thiết bị, IP, user-agent. Có sẵn trong hệ thống ngân hàng.",
        )

    def _build_aggregators(self) -> None:
        """Tầng gom tiền — hình thái fan-in kinh điển."""
        self.aggregators = []
        for i in range(3):
            eid = f"ACC-AGG-{i + 1}"
            self.add_entity(
                eid,
                "account",
                f"Tài khoản gom {i + 1}",
                subtitle=f"{BANKS[i]} •{self.rng.randint(1000, 9999)}",
                hub_id="HUB-SGN",
                risk=self.rng.randint(87, 94),
                first_day=18 + i * 2,
                attributes={"bank_code": BANKS[i], "fan_in_degree": len(self.mules) // 3},
            )
            self.aggregators.append(eid)

        for idx, m in enumerate(self.mules):
            agg = self.aggregators[idx % len(self.aggregators)]
            amount = round(self.rng.uniform(280_000, 1_100_000), 2)
            self.add_rel(m, agg, "transfer", label=f"${amount / 1e6:.2f}M", amount=amount, day=20 + idx * 0.4)

        self.add_observation(
            "EV-209",
            "BANK",
            20,
            "native_system",
            confidence=0.97,
            summary="Sao kê giao dịch tầng gom: fan-in từ 12 tài khoản về 3 tài khoản trong 9 ngày.",
        )
        # Báo cáo giao dịch đáng ngờ gửi FIU — mở quyền cho vai trò FIU muộn hơn
        # ngân hàng, vì nó chỉ tồn tại sau khi ngân hàng gửi báo cáo.
        self.add_observation(
            "EV-220",
            "FIU",
            33,
            "report",
            confidence=0.90,
            legal_basis="LB-PCRT-2022-D26",
            summary="Báo cáo giao dịch đáng ngờ do ngân hàng gửi, kèm danh sách tài khoản liên quan.",
        )

    def _build_p2p_and_crypto(self) -> None:
        """Chuyển đổi sang USDT rồi đi nhiều hop trước khi off-ramp.

        Liên kết giữa chân tiền đồng và chân on-chain chỉ là *ứng viên*: khớp
        được về số tiền và thời gian, nhưng không có bằng chứng trực tiếp nào
        nói hai chân đó là cùng một dòng tiền. `link_confidence` giữ đúng mức
        bất định đó (chương 10.4).
        """
        vendors = [
            ("PER-P2P-A", "P2P Vendor A", 76),
            ("PER-P2P-B", "P2P Vendor B", 72),
            ("PER-OTC-C", "OTC Desk C", 79),
        ]
        for idx, (eid, label, risk) in enumerate(vendors):
            self.add_entity(
                eid, "person", label, subtitle="đối tác P2P/OTC", hub_id="HUB-SGN", risk=risk, first_day=30 + idx
            )
            for agg in self.aggregators:
                amount = round(self.rng.uniform(400_000, 1_400_000), 2)
                self.add_rel(agg, eid, "transfer", label=f"${amount / 1e6:.2f}M", amount=amount, day=31 + idx)

        self.add_entity(
            "VASP-X",
            "vasp",
            "VASP Exchange X",
            subtitle="sàn nước ngoài",
            hub_id="HUB-SIN",
            risk=66,
            first_day=32,
            access_tier="REGULATOR",
        )

        # Ví USDT: 4 ví trung gian rồi hội tụ về ví operator.
        self.wallets: list[str] = []
        for i in range(4):
            addr = "T" + hashlib.sha256(f"{self.seed}-w{i}".encode()).hexdigest()[:33].upper()
            eid = f"WAL-{i + 1:02d}"
            self.add_entity(
                eid,
                "wallet",
                f"{addr[:6]}…{addr[-4:]}",
                subtitle="USDT TRC20",
                hub_id="HUB-HKG",
                risk=self.rng.randint(76, 84),
                first_day=33 + i,
                attributes={"address": addr, "chain": "tron"},
            )
            self.wallets.append(addr)

        op_addr = "T" + hashlib.sha256(f"{self.seed}-op".encode()).hexdigest()[:33].upper()
        self.add_entity(
            "WAL-OP",
            "wallet",
            f"{op_addr[:6]}…{op_addr[-4:]}",
            subtitle="ví operator nghi vấn",
            hub_id="HUB-HKG",
            risk=96,
            first_day=38,
            attributes={"address": op_addr, "chain": "tron"},
        )

        # Chuyển on-chain: mỗi ví trung gian gửi về ví operator sau vài giờ.
        n_tx = 6 + self.scale * 6
        for i in range(n_tx):
            src = self.wallets[i % len(self.wallets)]
            day = 34 + i * (10 / max(1, n_tx - 1))
            amount = round(self.rng.uniform(45_000, 320_000), 2)
            self.w.crypto.append(
                {
                    "transfer_id": f"CTX-{i + 1:04d}",
                    "simulation_id": SIMULATION_ID,
                    "chain": "tron",
                    "tx_hash": hashlib.sha256(f"{self.seed}-tx{i}".encode()).hexdigest(),
                    "log_index": 0,
                    "from_address": src,
                    "to_address": op_addr,
                    "asset": "USDT",
                    "amount": amount,
                    "amount_usd": amount,
                    "block_time": self.jitter(self.at(day), 3),
                    "transfer_kind": "transfer",
                    # Khớp bank↔chain là suy luận, không phải quan sát.
                    "link_confidence": round(self.rng.uniform(0.55, 0.78), 2),
                }
            )

        for w in [*self.wallets, op_addr]:
            self.w.exposures.append(
                {
                    "exposure_id": f"EXP-{len(self.w.exposures) + 1:03d}",
                    "address": w,
                    "service_id": "SVC-P2P-GENERIC",
                    "service_type": "p2p",
                    "exposure_kind": "direct" if w == op_addr else "indirect",
                    "hops": 0 if w == op_addr else self.rng.randint(1, 3),
                    "confidence": round(self.rng.uniform(0.52, 0.81), 2),
                    "source_id": "PUBLIC_CHAIN_TRC20_USDT",
                    "known_from": self.at(35),
                    "valid_to": None,
                }
            )

        self.add_observation(
            "EV-216",
            "PUBLIC",
            34,
            "public",
            confidence=0.99,
            summary="Giao dịch USDT TRC20 công khai trên chuỗi — ai cũng đọc được, không cần quyền.",
        )
        self.add_observation(
            "EV-214",
            "BANK",
            31,
            "native_system",
            confidence=0.88,
            summary="Chuyển khoản từ tài khoản gom sang tài khoản đối tác P2P/OTC.",
        )
        # Phản hồi của VASP chỉ có khi có yêu cầu chính thức — mốc mở quyền muộn.
        self.add_observation(
            "EV-218",
            "LAW_ENFORCEMENT",
            41,
            "cooperation",
            confidence=0.82,
            legal_basis="LB-MLAT-2026-014",
            custody="COC-2026-0341-01",
            redaction="pii_masked",
            summary="Phản hồi hợp tác của VASP: hồ sơ KYC và lịch sử rút của tài khoản liên quan.",
        )

    def _build_hard_negatives(self) -> None:
        """Thực thể hợp pháp trông giống đối tượng nghi vấn.

        Không có chúng thì mọi chỉ số đều đẹp một cách vô nghĩa: mô hình gắn cờ
        tất cả và vẫn đạt recall 100%. Chương 10.2 gọi đây là hard negative bắt
        buộc phải có.
        """
        self.add_entity(
            "ACC-PAYROLL",
            "account",
            "Tài khoản chi lương",
            subtitle="VPB •2210 — doanh nghiệp có đăng ký",
            hub_id="HUB-SGN",
            risk=15,
            first_day=4,
            hard_negative=True,
            attributes={"note": "Fan-out nhiều người nhận hàng tháng, hình thái giống chi trả mule."},
        )
        self.add_entity(
            "ORG-MERCHANT",
            "organisation",
            "Siêu thị Minh Long",
            subtitle="merchant hợp pháp, doanh thu tiền mặt cao",
            hub_id="HUB-SGN",
            risk=18,
            first_day=5,
            hard_negative=True,
            attributes={"note": "Nộp tiền mặt đều đặn, dễ bị luật ngưỡng gắn cờ nhầm."},
        )
        self.add_entity(
            "PER-TRADER",
            "person",
            "Nhà đầu tư P2P hợp pháp",
            subtitle="giao dịch stablecoin có kê khai",
            hub_id="HUB-HAN",
            risk=24,
            first_day=12,
            hard_negative=True,
            attributes={"note": "Mua bán USDT thường xuyên nhưng nguồn tiền chứng minh được."},
        )

    def _build_corridors(self) -> None:
        """Tổng hợp dòng tiền theo hành lang cho World Monitor."""
        specs = [
            ("HUB-PNH", "HUB-SGN", "gamb", "VND", 12_400_000, 1842, 92, "TYP-GMB-01"),
            ("HUB-SGN", "HUB-SIN", "p2p", "USDT", 8_100_000, 926, 88, "TYP-GMB-01"),
            ("HUB-SIN", "HUB-HKG", "chain", "USDT", 6_800_000, 312, 71, None),
            ("HUB-HAN", "HUB-SGN", "bank", "VND", 4_200_000, 2210, 66, "TYP-FRD-02"),
            ("HUB-SGN", "HUB-BKK", "p2p", "USDT", 2_900_000, 480, 63, None),
            ("HUB-HKG", "HUB-DXB", "vasp", "USDT", 5_500_000, 188, 61, None),
            ("HUB-SGN", "HUB-HKG", "chain", "USDT", 9_600_000, 204, 34, None),
            ("HUB-SIN", "HUB-SGN", "bank", "USD", 64_000_000, 5120, 18, None),
            ("HUB-DAD", "HUB-SGN", "bank", "VND", 3_100_000, 1450, 22, None),
            ("HUB-BKK", "HUB-SIN", "bank", "USD", 21_000_000, 1730, 15, None),
        ]
        for i, (s, t, ch, cur, vol, txn, risk, typ) in enumerate(specs):
            self.w.corridors.append(
                {
                    "corridor_id": f"COR-{i + 1:03d}",
                    "simulation_id": SIMULATION_ID,
                    "source_hub_id": s,
                    "target_hub_id": t,
                    "channel": ch,
                    "currency": cur,
                    "volume_usd": vol,
                    "txn_count": txn,
                    "risk_score": risk,
                    "typology_hint": typ,
                    "alert_count": 3 if risk >= 85 else 1 if risk >= 60 else 0,
                    "first_seen": self.at(self.rng.uniform(0, 8)),
                    "last_seen": self.at(WORLD_DAYS - self.rng.uniform(0, 2)),
                }
            )

    def _build_ground_truth(self) -> None:
        """Thế giới ẩn: vai trò thật, ledger cược, và các mốc phát hiện."""
        roles = [
            ("PLAT-LS88", "operator"),
            ("PSP-GATE", "service"),
            ("PSP-FAST", "service"),
            ("POOL-A", "player"),
            ("POOL-B", "player"),
        ]
        roles += [(m, "mule") for m in self.mules]
        roles += [(o, "coordinator" if i == 0 else "mule") for i, o in enumerate(self.owners)]
        roles += [("PER-P2P-A", "broker"), ("PER-P2P-B", "broker"), ("PER-OTC-C", "broker")]
        roles += [("ACC-AGG-1", "coordinator"), ("ACC-AGG-2", "coordinator"), ("ACC-AGG-3", "mule")]
        # Hard negative có vai trò thật là "vô can" — đây chính là đáp án dùng
        # để đo tỷ lệ dương tính giả.
        roles += [("ACC-PAYROLL", "innocent"), ("ORG-MERCHANT", "innocent"), ("PER-TRADER", "innocent")]

        for eid, role in roles:
            self.w.gt_roles.append(
                {"simulation_id": SIMULATION_ID, "entity_id": eid, "case_id": CASE_ID, "true_role": role}
            )

        # Ledger cược — tồn tại trong thế giới thật, ngân hàng không thấy.
        n = 40 + self.scale * 20
        for i in range(n):
            self.w.gt_ledger.append(
                {
                    "ledger_id": f"GLG-{i + 1:04d}",
                    "simulation_id": SIMULATION_ID,
                    "case_id": CASE_ID,
                    "operator_id": "PLAT-LS88",
                    "player_id": f"PLR-{i % 25 + 1:03d}",
                    "agent_id": f"AGT-{i % 4 + 1}",
                    "event_kind": ["deposit", "chip_convert", "bet", "payout", "settlement"][i % 5],
                    "event_time": self.jitter(self.at(self.rng.uniform(0, WORLD_DAYS)), 6),
                    "true_value_usd": round(self.rng.uniform(50, 25_000), 2),
                }
            )

        # Các mốc tín hiệu sớm nhất theo từng vai trò. Khoảng cách giữa
        # first_illicit_event_time (ngày 0) và các mốc này là thứ benchmark đo.
        signals = [
            ("BANK", 20, "Fan-in bất thường về tài khoản gom — vượt ngưỡng luật velocity."),
            ("FIU", 33, "Nhận báo cáo giao dịch đáng ngờ từ ngân hàng."),
            ("PUBLIC", 34, "Cụm ví USDT nhận tiền hội tụ, quan sát được on-chain."),
            ("REGULATOR", 36, "Đối chiếu báo cáo nhiều tổ chức, thấy trùng đối tác P2P."),
            ("LAW_ENFORCEMENT", 41, "VASP phản hồi yêu cầu hợp tác, xác định chủ tài khoản rút."),
        ]
        for role, day, desc in signals:
            self.w.gt_signals.append(
                {"case_id": CASE_ID, "observer_role": role, "signal_time": self.at(day), "signal_desc": desc}
            )

        self.w.gt_case = {
            "case_id": CASE_ID,
            "simulation_id": SIMULATION_ID,
            "scenario_type": SCENARIO,
            "network_id": NETWORK_ID,
            "predicate_offence": "gambling",
            "first_illicit_event_time": self.at(0),
            "confirmation_time": self.at(41),
            "true_value_flow_usd": 12_400_000,
            # Bằng chứng agent ĐƯỢC viện dẫn.
            "observable_evidence_refs": ["EV-201", "EV-209", "EV-211", "EV-214", "EV-216", "EV-220"],
            # Bằng chứng CẤM dùng khi suy luận.
            "hidden_only_refs": ["GT-LEDGER", "GT-ROLES"],
            "counterfactual_run_ids": [],
        }

    def _build_operational(self) -> None:
        """Chiếu thế giới mô phỏng sang các bảng vận hành của console.

        Đây là bước biến dữ liệu ABM thành thứ *dùng được*: nếu case chỉ nằm
        trong schema `fc` thì nó là một tập dữ liệu đẹp mà không màn hình nghiệp
        vụ nào chạm tới. Chiếu sang `customer`/`account`/`transaction`/`alert`/
        `aml_case`/`evidence` thì analyst mở Alert Center, Case workspace và
        Transaction Explorer là thấy ngay, đi hết được quy trình tới SAR.

        Chỉ chiếu phần **quan sát được**. Nền tảng cá cược, người chơi và ledger
        không có mặt ở đây — đúng như chương 10.3: ngân hàng chưa biết đây là
        đường dây đánh bạc, họ chỉ thấy một mạng lưới thu hộ bất thường.
        """
        # Một khách hàng pháp nhân đại diện cho cụm tài khoản bị lợi dụng.
        # Dùng prototype `shell_entity` vì đó là hồ sơ mà cụm này trông giống.
        cust_id = "CUS-ABM-0341"
        self.w.customers.append(
            {
                "customer_id": cust_id,
                "customer_type": "individual",
                "prototype": "shell_entity",
                "occupation": "Không kê khai",
                "declared_income_band": "0-15tr",
                "expected_monthly_volume": 50_000_000,
                "registered_country": "VN",
                "onboarding_date": self.at(1).date(),
                # Suy từ nguyên mẫu và quốc gia, KHÔNG suy từ nhãn rửa tiền (ND1).
                "risk_rating": "high",
            }
        )

        # Tài khoản thật cho các thực thể loại `account` của thế giới mô phỏng.
        # `account_key` phải đúng dạng <bank>:<số> theo ràng buộc CHECK.
        #
        # Số tài khoản băm bằng blake2b chứ không bằng `hash()`: Python bật
        # randomization cho hash của chuỗi, nên mỗi tiến trình cho ra một số
        # khác nhau. Với một khoá dùng để *nối* thực thể trong đồ thị với giao
        # dịch trong sổ cái, không ổn định nghĩa là không nối lại được — và đó
        # đúng là lý do màn đồ thị mạng lưới cho tới nay không có giao dịch nào
        # đứng sau cạnh nào.
        #
        # Mapping còn được ghi ngược vào `fc.entity.attributes.account_key`, để
        # truy vấn về sau join được mà không phải chạy lại bộ sinh.
        self.acct_of: dict[str, str] = {}
        for ent in self.w.entities:
            if ent["entity_type"] != "account":
                continue
            attrs = json.loads(ent["attributes"]) if ent["attributes"] else {}
            bank = attrs.get("bank_code") or BANKS[len(self.acct_of) % len(BANKS)]
            digest = hashlib.blake2b(ent["entity_id"].encode(), digest_size=6).digest()
            number = f"{int.from_bytes(digest, 'big') % 9_000_000 + 1_000_000}"
            key = f"{bank}:{number}"
            self.acct_of[ent["entity_id"]] = key
            attrs["account_key"] = key
            ent["attributes"] = json.dumps(attrs, ensure_ascii=False)
            self.w.accounts.append(
                {
                    "account_key": key,
                    "customer_id": cust_id,
                    "bank_code": bank,
                    "account_number": number,
                    "opened_at": ent["first_seen"].date(),
                    "status": "active",
                }
            )

        # Giao dịch: mỗi quan hệ `transfer` giữa hai tài khoản thành một chuỗi
        # chuyển khoản nhỏ, không phải một cục. Chia nhỏ mới ra được hình thái
        # velocity mà luật phát hiện dựa vào.
        subject_key = self.acct_of.get("ACC-AGG-1")
        for rel in self.w.relationships:
            if rel["kind"] != "transfer":
                continue
            src = self.acct_of.get(rel["source_id"])
            dst = self.acct_of.get(rel["target_id"])
            if not src or not dst or src == dst:
                continue
            total = float(rel["amount_usd"] or 0)
            if total <= 0:
                continue
            parts = self.rng.randint(3, 6)
            for k in range(parts):
                moment = rel["known_from"] + timedelta(hours=self.rng.uniform(0, 60))
                amount = round(total / parts * self.rng.uniform(0.82, 1.18), 2)
                self.w.transactions.append(
                    {
                        "occurred_at": moment,
                        "from_account_key": src,
                        "to_account_key": dst,
                        "amount": amount,
                        "currency": "USD",
                        "amount_received": amount,
                        "receiving_currency": "USD",
                        "channel": "transfer",
                        "remarks": "",
                        # Chia tập theo thời gian, không ngẫu nhiên (ND2).
                        "dataset_split": "test",
                    }
                )

        # Vụ việc. Trạng thái `ChoNguoiPheDuyet` khớp với việc agent kết thúc ở
        # `needs_human` — hai chỗ nói cùng một câu chuyện.
        self.w.case_row = {
            "case_id": CASE_ID,
            "subject_account_key": subject_key,
            "title": "Đường dây thu hộ nhiều tầng — chuyển đổi USDT",
            "state": "ChoNguoiPheDuyet",
            "risk_score": 94.0,
            "priority": "critical",
            "assigned_to": "L.T. Vy",
            "created_at": self.at(33),
            "updated_at": self.at(WORLD_DAYS - 0.5),
        }

        # Cảnh báo trên các tài khoản gom. T04 = fan-in/fan-out theo danh mục
        # typology hiện có của hệ thống.
        for i, agg in enumerate(self.aggregators):
            key = self.acct_of.get(agg)
            if not key:
                continue
            alert_id = f"ALR-ABM-{i + 1:03d}"
            score = 92.0 - i * 3
            self.w.alerts.append(
                {
                    "alert_id": alert_id,
                    "account_key": key,
                    "transaction_id": None,
                    "typology_code": "T04",
                    "detector": "graph" if i == 0 else "rule",
                    "risk_score": score,
                    "status": "grouped",
                    "case_id": CASE_ID,
                    "created_at": self.at(33 + i * 0.3),
                }
            )
            # NT7: mỗi cảnh báo phải có tối thiểu ba yếu tố đóng góp có giá trị số.
            for code, label, contrib, weight in [
                ("FAN_IN_DEGREE", "Số tài khoản nguồn đổ về trong 7 ngày", 34.0, 0.35),
                ("ACCOUNT_AGE", "Tuổi tài khoản nguồn dưới 45 ngày", 22.0, 0.20),
                ("DEVICE_REUSE", "Nhiều tài khoản dùng chung thiết bị", 19.0, 0.20),
                ("VELOCITY", "Tiền vào ra trong dưới 24 giờ", 17.0, 0.25),
            ]:
                self.w.alert_reasons.append(
                    {
                        "alert_id": alert_id,
                        "factor_code": code,
                        "factor_label": label,
                        "contribution": contrib,
                        "weight": weight,
                    }
                )

        # Bằng chứng gắn vào vụ việc. Lọc theo *vai trò quan sát*, không chỉ
        # theo cờ hiển thị: đây là hồ sơ của một tổ chức tài chính, nên nó chỉ
        # được chứa thứ mà ngân hàng thực sự nhìn thấy, cộng với dữ liệu công
        # khai. Bằng chứng thu giữ hoặc do hợp tác quốc tế thuộc tầng điều tra —
        # đưa vào đây là đúng loại rò rỉ mà chương 4 cảnh báo.
        for obs in self.w.observations:
            if not obs["is_visible_to_model"] or obs["observer_role"] not in BANK_VISIBLE_ROLES:
                continue
            payload = {
                "evidence_item_id": obs["evidence_item_id"],
                "observer_role": obs["observer_role"],
                "acquisition_type": obs["acquisition_type"],
                "summary": obs["summary"],
                "source_confidence": obs["source_confidence"],
            }
            blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            self.w.evidences.append(
                {
                    "evidence_id": f"EVD-{obs['evidence_item_id']}",
                    "case_id": CASE_ID,
                    "source_table": "fc.observation_event",
                    "source_ref": obs["observation_event_id"],
                    "payload": blob,
                    "retrieved_at": obs["available_from"],
                    "evidence_hash": hashlib.sha256(blob.encode()).hexdigest(),
                }
            )

    def _build_agent_run(self) -> None:
        """Một lần chạy của agent tầng A (tổ chức tài chính).

        Kết thúc ở `needs_human` chứ không phải `succeeded`: chương 11 đặt
        human-in-the-loop là bắt buộc, agent không tự kết luận vụ việc.
        """
        run_id = "RUN-2026-0341-01"
        start = self.at(33.2)
        self.w.agent_runs.append(
            {
                "run_id": run_id,
                "simulation_id": SIMULATION_ID,
                "case_id": CASE_ID,
                "alert_id": None,
                "agent_tier": "A_INSTITUTION",
                "started_at": start,
                "finished_at": start + timedelta(seconds=182),
                "status": "needs_human",
                "model_version": "fusion-v2.4.1",
                "conclusion": (
                    "Mạng lưới thu hộ nhiều tầng phù hợp typology TYP-GMB-01. Bằng chứng quan sát được "
                    "đủ để đề xuất lập hồ sơ nghi vấn; chưa đủ để kết luận nguồn tiền là đánh bạc — "
                    "kết luận đó cần dữ liệu điều tra mà vai trò hiện tại không có quyền truy cập."
                ),
                "confidence": 0.79,
                "token_cost": 41_200,
            }
        )
        steps = [
            ("fetch_alert_context", "alert_id=ALR-2026-4801", "12 cảnh báo cùng cụm tài khoản", "ok", 240, ["EV-201"]),
            ("expand_entity_graph", "seed=ACC-AGG-1, depth=2", "26 thực thể, 61 quan hệ", "ok", 1850, ["EV-209"]),
            (
                "device_correlation",
                "accounts=12",
                "3 cụm thiết bị; 1 cụm độ tin cậy thấp do NAT",
                "ok",
                620,
                ["EV-211"],
            ),
            ("screen_watchlist", "entities=26", "Không có khớp trừng phạt/PEP", "ok", 310, []),
            (
                "trace_crypto_exposure",
                "addresses=5",
                "Phơi nhiễm P2P gián tiếp 1–3 hop, độ tin cậy 0.52–0.81",
                "ok",
                2100,
                ["EV-216"],
            ),
            (
                "request_vasp_records",
                "vasp=VASP-X",
                "Từ chối: vai trò A_INSTITUTION không có thẩm quyền yêu cầu",
                "blocked",
                90,
                [],
            ),
            (
                "draft_str_narrative",
                "case=CASE-2026-0341",
                "Bản nháp 6 đoạn, 23 tham chiếu bằng chứng",
                "ok",
                3400,
                ["EV-201", "EV-209", "EV-214"],
            ),
            ("request_human_review", "priority=P1", "Chuyển hàng đợi phê duyệt cho MLRO", "ok", 120, []),
        ]
        for i, (tool, inp, out, status, ms, refs) in enumerate(steps):
            self.w.agent_steps.append(
                {
                    "step_id": f"{run_id}-S{i + 1:02d}",
                    "run_id": run_id,
                    "step_index": i,
                    "tool_name": tool,
                    "input_summary": inp,
                    "output_summary": out,
                    "status": status,
                    "started_at": start + timedelta(seconds=sum(s[4] for s in steps[:i]) / 1000),
                    "duration_ms": ms,
                    "evidence_refs": refs,
                }
            )

    def _build_benchmarks(self) -> None:
        """Chỉ số kiểm định theo chương 15.1 — không có accuracy.

        `detection_lead_time_days` là chỉ số riêng của thiết kế này: bao nhiêu
        ngày trước `confirmation_time` thì mô hình đã gắn cờ. Đó mới là giá trị
        vận hành, chứ không phải đường ROC.
        """
        metrics = [
            ("precision_at_50", 0.62, 0.55),
            ("recall_at_50", 0.48, 0.40),
            ("false_positive_rate_hard_negative", 0.11, 0.15),
            ("detection_lead_time_days", 21.0, 14.0),
            ("alert_to_case_conversion", 0.34, 0.25),
            ("evidence_coverage", 0.86, 0.80),
        ]
        for name, value, target in metrics:
            self.w.benchmarks.append(
                {
                    "result_id": f"BM-{SCENARIO}-{name}",
                    "simulation_id": SIMULATION_ID,
                    "task_id": f"TASK-{SCENARIO}-EARLY-DETECT",
                    "scenario_package": SCENARIO,
                    "model_version": "fusion-v2.4.1",
                    "split": "test",
                    "metric_name": name,
                    "metric_value": value,
                    "target_value": target,
                    "evaluated_at": self.at(WORLD_DAYS - 1),
                }
            )

    def _build_monitoring(self) -> None:
        """14 ngày theo dõi mô hình, có một chỉ số chớm vượt ngưỡng."""
        base = {"alert_volume": 180.0, "psi_amount": 0.08, "avg_risk_score": 61.0, "p95_latency_ms": 820.0}
        for day in range(14):
            observed = self.at(WORLD_DAYS - 14 + day)
            for metric, start in base.items():
                # Trôi tăng dần ở psi_amount để màn hình Model Monitoring có
                # một trường hợp thật sự đáng nhìn, không phải toàn màu xanh.
                drift = day * 0.012 if metric == "psi_amount" else 0.0
                value = start + drift + self.rng.uniform(-start * 0.04, start * 0.04)
                psi = round(start + drift, 4) if metric == "psi_amount" else None
                status = "ok"
                if metric == "psi_amount":
                    status = "breach" if value >= 0.25 else "watch" if value >= 0.20 else "ok"
                self.w.monitors.append(
                    {
                        "monitor_id": f"MON-{metric}-{day:02d}",
                        "model_version": "fusion-v2.4.1",
                        "observed_at": observed,
                        "metric_name": metric,
                        "metric_value": round(value, 4),
                        "drift_score": psi,
                        "status": status,
                    }
                )

    def _build_data_quality(self) -> None:
        """Kiểm tra chất lượng theo 5 chiều của chương 12.1."""
        checks = [
            ("fc.entity", "entity_id không rỗng và duy nhất", "uniqueness", 100.0, 100.0),
            ("fc.relationship", "cạnh suy luận có confidence và diễn giải", "validity", 100.0, 100.0),
            ("fc.crypto_transfer", "block_time nằm trong cửa sổ mô phỏng", "validity", 100.0, 99.0),
            ("fc.observation_event", "available_from không sớm hơn sự kiện gốc", "consistency", 100.0, 100.0),
            ("public.transaction", "amount > 0 và có tiền tệ hợp lệ", "validity", 99.8, 99.5),
            ("fc.corridor_flow", "hai đầu hành lang khác nhau", "consistency", 100.0, 100.0),
            ("fc.exposure_label", "known_from không muộn hơn thời điểm dùng", "timeliness", 97.4, 95.0),
            ("fc.entity", "trường subtitle được điền", "completeness", 92.1, 90.0),
        ]
        for i, (dataset, name, dim, rate, threshold) in enumerate(checks):
            rows = self.rng.randint(400, 9000)
            failed = int(rows * (100 - rate) / 100)
            self.w.dq_checks.append(
                {
                    "check_id": f"DQ-{i + 1:03d}",
                    "simulation_id": SIMULATION_ID,
                    "dataset": dataset,
                    "check_name": name,
                    "dimension": dim,
                    "observed_at": self.at(WORLD_DAYS - 0.2),
                    "pass_rate": rate,
                    "threshold": threshold,
                    "rows_checked": rows,
                    "rows_failed": failed,
                    "status": "ok" if rate >= threshold else "warn" if rate >= threshold - 3 else "fail",
                    "detail": "" if rate >= threshold else f"{failed} bản ghi không đạt.",
                }
            )

    def _build_token_project(self) -> None:
        """Một dự án token để màn hình Project Risk có dữ liệu.

        Thuộc kịch bản VN-CA-01, đưa vào cùng lần chạy này để giao diện không
        rỗng; nó không tham gia vào ground truth của case VN-CA-03.
        """
        self.w.projects.append(
            {
                "project_id": "PRJ-LUXP",
                "simulation_id": SIMULATION_ID,
                "name": "LUXP Protocol",
                "symbol": "LUXP",
                "chain": "bsc",
                "contract_address": "0x" + hashlib.sha256(f"{self.seed}-luxp".encode()).hexdigest()[:40],
                "deployer_address": "0x" + hashlib.sha256(f"{self.seed}-dep".encode()).hexdigest()[:40],
                "launched_at": self.at(6),
                "holder_gini": 0.914,
                "liquidity_usd": 148_000,
                "liquidity_removed_pct": 96.5,
                "privileged_functions": ["mint", "pause", "setFee", "blacklist"],
                "kol_channels": 8,
                "domain_age_days": 34,
                "risk_score": 88,
                "status": "investigating",
            }
        )


# ---------------------------------------------------------------------
# Ghi xuống cơ sở dữ liệu
# ---------------------------------------------------------------------


def _insert(session: Session, sql: str, rows: list[dict[str, Any]]) -> None:
    if rows:
        session.execute(text(sql), rows)


def check_schema(session: Session) -> None:
    """Dừng sớm với thông báo rõ ràng nếu chưa áp migration 005."""
    exists = session.execute(text("SELECT to_regclass('fc.simulation_run') IS NOT NULL")).scalar()
    if not exists:
        raise SystemExit(
            "Chưa có schema `fc`. Chạy `python scripts/migrate.py` trước "
            "(hoặc `make db-reset` nếu chấp nhận mất dữ liệu)."
        )


def wipe(session: Session) -> None:
    """Xoá lần chạy cũ. Khoá ngoại ON DELETE CASCADE lo phần lớn công việc."""
    # fc_gt.case_ground_truth tham chiếu simulation_run nên cũng bị cuốn theo.
    session.execute(text("DELETE FROM fc.simulation_run WHERE simulation_id = :sid"), {"sid": SIMULATION_ID})
    # Các bảng fc không gắn simulation_id phải xoá tay.
    session.execute(text("DELETE FROM fc.exposure_label WHERE source_id = 'PUBLIC_CHAIN_TRC20_USDT'"))
    session.execute(text("DELETE FROM fc.model_monitor WHERE model_version = 'fusion-v2.4.1'"))
    # Ba bảng dưới đây khai báo `simulation_id ... ON DELETE SET NULL` chứ không
    # CASCADE — cố ý, vì một lượt chạy agent hay một kết quả benchmark đã diễn ra
    # thì không được biến mất chỉ vì mô phỏng bị dựng lại. Nhưng hệ quả là xoá
    # simulation xong các dòng cũ vẫn nằm đó với nguyên khoá chính, và lần nạp
    # sau đâm thẳng vào unique constraint. Xoá tường minh theo tiền tố ID mà
    # generator này sinh ra; `fc.agent_step` đi theo `fc.agent_run` bằng CASCADE.
    session.execute(text("DELETE FROM fc.agent_run WHERE run_id LIKE 'RUN-2026-0341-%'"))
    session.execute(text("DELETE FROM fc.benchmark_result WHERE result_id LIKE 'BM-VN-CA-03-%'"))
    session.execute(
        text("DELETE FROM fc.data_quality_check WHERE simulation_id = :sid OR check_id LIKE 'DQ-%'"),
        {"sid": SIMULATION_ID},
    )

    # Bảng vận hành: xoá theo đúng thứ tự khoá ngoại, từ lá vào gốc. Chỉ đụng
    # tới dữ liệu do generator này tạo — không chạm dữ liệu seed.
    cid = {"cid": CASE_ID, "cust": "CUS-ABM-0341"}

    # `evidence`, `audit_log` và `approval` bị chặn xoá ở tầng cơ sở dữ liệu
    # (002_audit_immutability.sql). Đó là ràng buộc pháp lý, không phải trở
    # ngại kỹ thuật để đi vòng: bằng chứng đã ghi thì không được biến mất.
    #
    # Vì `evidence_id` sinh tất định từ `evidence_item_id`, chạy lại chỉ bỏ qua
    # các dòng đã có (ON CONFLICT DO NOTHING) chứ không nhân bản. Rủi ro còn
    # lại là dòng cũ do phiên bản generator trước tạo ra và nay không còn hợp
    # lệ; `check_invariants` sẽ phát hiện và báo phải dựng lại cơ sở dữ liệu.
    stale = session.execute(text("SELECT count(*) FROM evidence WHERE case_id = :cid"), {"cid": CASE_ID}).scalar_one()
    if stale:
        log.info("Giữ lại %d bằng chứng đã ghi của %s (bảng chỉ ghi thêm).", stale, CASE_ID)

    session.execute(text("DELETE FROM alert_reason WHERE alert_id LIKE 'ALR-ABM-%'"))
    session.execute(text("DELETE FROM alert WHERE case_id = :cid"), cid)
    session.execute(
        text(
            """DELETE FROM transaction
                WHERE from_account_key IN (SELECT account_key FROM account WHERE customer_id = :cust)
                   OR to_account_key   IN (SELECT account_key FROM account WHERE customer_id = :cust)"""
        ),
        cid,
    )
    session.execute(text("DELETE FROM aml_case WHERE case_id = :cid"), cid)
    session.execute(text("DELETE FROM account WHERE customer_id = :cust"), cid)
    session.execute(text("DELETE FROM customer WHERE customer_id = :cust"), cid)


def write(session: Session, gen: Generator, w: World) -> None:
    session.execute(
        text(
            """INSERT INTO fc.simulation_run
                 (simulation_id, scenario_package, seed, schema_version, parameter_set_id,
                  generator_version, world_from, world_to, notes)
               VALUES (:sid, :pkg, :seed, :schema, :pset, :gen, :wfrom, :wto, :notes)"""
        ),
        {
            "sid": SIMULATION_ID,
            "pkg": SCENARIO,
            "seed": gen.seed,
            "schema": SCHEMA_VERSION,
            "pset": PARAMETER_SET_ID,
            "gen": GENERATOR_VERSION,
            "wfrom": gen.t0,
            "wto": gen.now,
            "notes": "Kịch bản VN-CA-03 (đánh bạc + rửa tiền), quy mô thử nghiệm.",
        },
    )

    _insert(
        session,
        """INSERT INTO fc.source_registry
             (source_id, source_type, scope, period, jurisdiction, fields_supported, transformation,
              confidence, rationale, access_level, owner, reviewer, valid_from, valid_to, prohibited_uses)
           VALUES (:source_id, :source_type, :scope, :period, :jurisdiction, :fields_supported,
                   :transformation, :confidence, :rationale, :access_level, :owner, :reviewer,
                   CAST(:valid_from AS date), CAST(:valid_to AS date), :prohibited_uses)
           ON CONFLICT (source_id) DO NOTHING""",
        SOURCES,
    )

    _insert(
        session,
        """INSERT INTO fc.hub (hub_id, name, country_code, lat, lon, jurisdiction_risk, known_from)
           VALUES (:hub_id, :name, :cc, :lat, :lon, :risk, CAST(:known_from AS date))
           ON CONFLICT (hub_id) DO NOTHING""",
        [
            {
                "hub_id": h[0],
                "name": h[1],
                "cc": h[2],
                "lat": h[3],
                "lon": h[4],
                "risk": h[5],
                "known_from": "2026-01-01",
            }
            for h in HUBS
        ],
    )

    # --- Bảng vận hành (schema public) ---
    # Ghi trước schema `fc` vì fc.agent_run có khoá ngoại tới aml_case.
    _insert(
        session,
        """INSERT INTO customer
             (customer_id, customer_type, prototype, occupation, declared_income_band,
              expected_monthly_volume, registered_country, onboarding_date, risk_rating)
           VALUES (:customer_id, :customer_type, :prototype, :occupation, :declared_income_band,
                   :expected_monthly_volume, :registered_country, :onboarding_date, :risk_rating)
           ON CONFLICT (customer_id) DO NOTHING""",
        w.customers,
    )

    _insert(
        session,
        """INSERT INTO account
             (account_key, customer_id, bank_code, account_number, opened_at, status)
           VALUES (:account_key, :customer_id, :bank_code, :account_number, :opened_at, :status)
           ON CONFLICT (account_key) DO NOTHING""",
        w.accounts,
    )

    _insert(
        session,
        """INSERT INTO transaction
             (occurred_at, from_account_key, to_account_key, amount, currency,
              amount_received, receiving_currency, channel, remarks, dataset_split)
           VALUES (:occurred_at, :from_account_key, :to_account_key, :amount, :currency,
                   :amount_received, :receiving_currency, :channel, :remarks, :dataset_split)""",
        w.transactions,
    )

    if w.case_row:
        session.execute(
            text(
                """INSERT INTO aml_case
                     (case_id, subject_account_key, title, state, risk_score, priority,
                      assigned_to, created_at, updated_at)
                   VALUES (:case_id, :subject_account_key, :title, :state, :risk_score,
                           :priority, :assigned_to, :created_at, :updated_at)
                   ON CONFLICT (case_id) DO NOTHING"""
            ),
            w.case_row,
        )

    _insert(
        session,
        """INSERT INTO alert
             (alert_id, account_key, transaction_id, typology_code, detector, risk_score,
              status, case_id, created_at)
           VALUES (:alert_id, :account_key, :transaction_id, :typology_code, :detector,
                   :risk_score, :status, :case_id, :created_at)
           ON CONFLICT (alert_id) DO NOTHING""",
        w.alerts,
    )

    _insert(
        session,
        """INSERT INTO alert_reason (alert_id, factor_code, factor_label, contribution, weight)
           VALUES (:alert_id, :factor_code, :factor_label, :contribution, :weight)
           ON CONFLICT (alert_id, factor_code) DO NOTHING""",
        w.alert_reasons,
    )

    _insert(
        session,
        """INSERT INTO evidence
             (evidence_id, case_id, source_table, source_ref, payload, retrieved_at, evidence_hash)
           VALUES (:evidence_id, :case_id, :source_table, :source_ref, CAST(:payload AS jsonb),
                   :retrieved_at, :evidence_hash)
           ON CONFLICT (evidence_id) DO NOTHING""",
        w.evidences,
    )

    _insert(
        session,
        """INSERT INTO fc.entity
             (entity_id, simulation_id, entity_type, label, subtitle, hub_id, risk_score,
              first_seen, last_seen, attributes, is_hard_negative, access_tier)
           VALUES (:entity_id, :simulation_id, :entity_type, :label, :subtitle, :hub_id,
                   :risk_score, :first_seen, :last_seen, CAST(:attributes AS jsonb),
                   :is_hard_negative, :access_tier)""",
        w.entities,
    )

    _insert(
        session,
        """INSERT INTO fc.relationship
             (relationship_id, simulation_id, source_id, target_id, kind, label, amount_usd,
              is_inferred, confidence, inference_logic, known_from, valid_to)
           VALUES (:relationship_id, :simulation_id, :source_id, :target_id, :kind, :label,
                   :amount_usd, :is_inferred, :confidence, :inference_logic, :known_from, :valid_to)""",
        w.relationships,
    )

    _insert(
        session,
        """INSERT INTO fc.corridor_flow
             (corridor_id, simulation_id, source_hub_id, target_hub_id, channel, currency,
              volume_usd, txn_count, risk_score, typology_hint, alert_count, first_seen, last_seen)
           VALUES (:corridor_id, :simulation_id, :source_hub_id, :target_hub_id, :channel, :currency,
                   :volume_usd, :txn_count, :risk_score, :typology_hint, :alert_count,
                   :first_seen, :last_seen)""",
        w.corridors,
    )

    _insert(
        session,
        """INSERT INTO fc.crypto_transfer
             (transfer_id, simulation_id, chain, tx_hash, log_index, from_address, to_address,
              asset, amount, amount_usd, block_time, transfer_kind, link_confidence)
           VALUES (:transfer_id, :simulation_id, :chain, :tx_hash, :log_index, :from_address,
                   :to_address, :asset, :amount, :amount_usd, :block_time, :transfer_kind,
                   :link_confidence)""",
        w.crypto,
    )

    _insert(
        session,
        """INSERT INTO fc.exposure_label
             (exposure_id, address, service_id, service_type, exposure_kind, hops, confidence,
              source_id, known_from, valid_to)
           VALUES (:exposure_id, :address, :service_id, :service_type, :exposure_kind, :hops,
                   :confidence, :source_id, :known_from, :valid_to)""",
        w.exposures,
    )

    _insert(
        session,
        """INSERT INTO fc.token_project
             (project_id, simulation_id, name, symbol, chain, contract_address, deployer_address,
              launched_at, holder_gini, liquidity_usd, liquidity_removed_pct, privileged_functions,
              kol_channels, domain_age_days, risk_score, status)
           VALUES (:project_id, :simulation_id, :name, :symbol, :chain, :contract_address,
                   :deployer_address, :launched_at, :holder_gini, :liquidity_usd,
                   :liquidity_removed_pct, :privileged_functions, :kol_channels, :domain_age_days,
                   :risk_score, :status)""",
        w.projects,
    )

    _insert(
        session,
        """INSERT INTO fc.observation_event
             (observation_event_id, simulation_id, evidence_item_id, observer_role, available_from,
              acquisition_type, legal_basis_id, redaction_profile, source_confidence,
              chain_of_custody_id, is_visible_to_model, summary)
           VALUES (:observation_event_id, :simulation_id, :evidence_item_id, :observer_role,
                   :available_from, :acquisition_type, :legal_basis_id, :redaction_profile,
                   :source_confidence, :chain_of_custody_id, :is_visible_to_model, :summary)""",
        w.observations,
    )

    _insert(
        session,
        """INSERT INTO fc.agent_run
             (run_id, simulation_id, case_id, alert_id, agent_tier, started_at, finished_at,
              status, model_version, conclusion, confidence, token_cost)
           VALUES (:run_id, :simulation_id, :case_id, :alert_id, :agent_tier, :started_at,
                   :finished_at, :status, :model_version, :conclusion, :confidence, :token_cost)""",
        w.agent_runs,
    )

    _insert(
        session,
        """INSERT INTO fc.agent_step
             (step_id, run_id, step_index, tool_name, input_summary, output_summary, status,
              started_at, duration_ms, evidence_refs)
           VALUES (:step_id, :run_id, :step_index, :tool_name, :input_summary, :output_summary,
                   :status, :started_at, :duration_ms, :evidence_refs)""",
        w.agent_steps,
    )

    _insert(
        session,
        """INSERT INTO fc.benchmark_result
             (result_id, simulation_id, task_id, scenario_package, model_version, split,
              metric_name, metric_value, target_value, evaluated_at)
           VALUES (:result_id, :simulation_id, :task_id, :scenario_package, :model_version, :split,
                   :metric_name, :metric_value, :target_value, :evaluated_at)""",
        w.benchmarks,
    )

    _insert(
        session,
        """INSERT INTO fc.model_monitor
             (monitor_id, model_version, observed_at, metric_name, metric_value, drift_score, status)
           VALUES (:monitor_id, :model_version, :observed_at, :metric_name, :metric_value,
                   :drift_score, :status)""",
        w.monitors,
    )

    _insert(
        session,
        """INSERT INTO fc.data_quality_check
             (check_id, simulation_id, dataset, check_name, dimension, observed_at, pass_rate,
              threshold, rows_checked, rows_failed, status, detail)
           VALUES (:check_id, :simulation_id, :dataset, :check_name, :dimension, :observed_at,
                   :pass_rate, :threshold, :rows_checked, :rows_failed, :status, :detail)""",
        w.dq_checks,
    )

    # --- ground truth: ghi sau cùng, vào schema riêng ---
    session.execute(
        text(
            """INSERT INTO fc_gt.case_ground_truth
                 (case_id, simulation_id, scenario_type, network_id, predicate_offence,
                  first_illicit_event_time, confirmation_time, true_value_flow_usd,
                  observable_evidence_refs, hidden_only_refs, counterfactual_run_ids)
               VALUES (:case_id, :simulation_id, :scenario_type, :network_id, :predicate_offence,
                       :first_illicit_event_time, :confirmation_time, :true_value_flow_usd,
                       :observable_evidence_refs, :hidden_only_refs, :counterfactual_run_ids)"""
        ),
        w.gt_case,
    )

    _insert(
        session,
        """INSERT INTO fc_gt.hidden_role (simulation_id, entity_id, case_id, true_role)
           VALUES (:simulation_id, :entity_id, :case_id, :true_role)
           ON CONFLICT DO NOTHING""",
        w.gt_roles,
    )

    _insert(
        session,
        """INSERT INTO fc_gt.first_observable_signal (case_id, observer_role, signal_time, signal_desc)
           VALUES (:case_id, :observer_role, :signal_time, :signal_desc)""",
        w.gt_signals,
    )

    _insert(
        session,
        """INSERT INTO fc_gt.hidden_gambling_ledger
             (ledger_id, simulation_id, case_id, operator_id, player_id, agent_id, event_kind,
              event_time, true_value_usd)
           VALUES (:ledger_id, :simulation_id, :case_id, :operator_id, :player_id, :agent_id,
                   :event_kind, :event_time, :true_value_usd)""",
        w.gt_ledger,
    )


def check_invariants(session: Session) -> None:
    """Kiểm tra rò rỉ theo phụ lục D. Sai một điều kiện là dữ liệu không dùng được."""
    problems: list[str] = []

    # 1. Mọi cạnh suy luận phải có độ tin cậy và diễn giải.
    n = session.execute(
        text(
            """SELECT count(*) FROM fc.relationship
                WHERE is_inferred AND (confidence IS NULL OR inference_logic IS NULL)"""
        )
    ).scalar_one()
    if n:
        problems.append(f"{n} quan hệ suy luận thiếu confidence hoặc diễn giải")

    # 2. Bằng chứng không được mở quyền trước khi thế giới mô phỏng bắt đầu.
    n = session.execute(
        text(
            """SELECT count(*) FROM fc.observation_event o
                 JOIN fc.simulation_run r USING (simulation_id)
                WHERE o.available_from < r.world_from"""
        )
    ).scalar_one()
    if n:
        problems.append(f"{n} bằng chứng có available_from sớm hơn mốc bắt đầu thế giới")

    # 3. Tín hiệu quan sát được không thể có trước hành vi.
    n = session.execute(
        text(
            """SELECT count(*) FROM fc_gt.first_observable_signal s
                 JOIN fc_gt.case_ground_truth g USING (case_id)
                WHERE s.signal_time < g.first_illicit_event_time"""
        )
    ).scalar_one()
    if n:
        problems.append(f"{n} tín hiệu quan sát được xảy ra trước hành vi đầu tiên")

    # 4. Bằng chứng chỉ có ở tầng điều tra không được lọt vào view ngân hàng.
    n = session.execute(
        text(
            """SELECT count(*) FROM fc.observation_event
                WHERE observer_role = 'BANK' AND acquisition_type IN ('seizure', 'cooperation')"""
        )
    ).scalar_one()
    if n:
        problems.append(f"{n} bằng chứng thu giữ/hợp tác lại nằm trong view BANK")

    # 5. Hồ sơ vụ việc của tổ chức tài chính không được chứa bằng chứng tầng
    #    điều tra. Đây là điều kiện dễ vi phạm nhất khi thêm nguồn dữ liệu mới.
    n = session.execute(
        text(
            """SELECT count(*) FROM evidence e
                 JOIN fc.observation_event o ON o.observation_event_id = e.source_ref
                WHERE e.case_id = :cid AND o.observer_role NOT IN ('BANK', 'PUBLIC')"""
        ),
        {"cid": CASE_ID},
    ).scalar_one()
    if n:
        problems.append(
            f"{n} bằng chứng tầng điều tra lọt vào hồ sơ vụ việc của ngân hàng. "
            "Bảng evidence chỉ ghi thêm nên không xoá được — dựng lại cơ sở dữ liệu "
            "(`make db-reset`) rồi chạy lại generator."
        )

    # 6. Phải có hard negative, nếu không mọi chỉ số đều vô nghĩa.
    n = session.execute(
        text("SELECT count(*) FROM fc.entity WHERE is_hard_negative AND simulation_id = :sid"),
        {"sid": SIMULATION_ID},
    ).scalar_one()
    if n < 3:
        problems.append(f"chỉ có {n} hard negative — cần tối thiểu 3 để đo dương tính giả")

    if problems:
        raise SystemExit("Kiểm tra rò rỉ thất bại:\n  - " + "\n  - ".join(problems))
    log.info("Kiểm tra rò rỉ (phụ lục D): đạt cả 6 điều kiện.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--scale", type=int, default=1, help="Hệ số quy mô (1 = nhỏ nhất)")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in thống kê, không ghi")
    parser.add_argument("--force", action="store_true", help="Xoá lần chạy cũ cùng ID rồi nạp lại")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    gen = Generator(seed=args.seed, scale=max(1, args.scale))
    world = gen.build()

    log.info("Kịch bản %s · seed %d · %d ngày mô phỏng", SCENARIO, args.seed, WORLD_DAYS)
    for name, count in world.counts().items():
        log.info("  %-22s %6d", name, count)

    if args.dry_run:
        log.info("--dry-run: không ghi gì xuống cơ sở dữ liệu.")
        return 0

    with get_session() as session:
        check_schema(session)
        exists = session.execute(
            text("SELECT count(*) FROM fc.simulation_run WHERE simulation_id = :sid"),
            {"sid": SIMULATION_ID},
        ).scalar_one()
        if exists and not args.force:
            log.info("Lần chạy %s đã tồn tại. Dùng --force để nạp lại.", SIMULATION_ID)
            return 0
        if exists:
            log.info("Xoá lần chạy cũ %s…", SIMULATION_ID)
            wipe(session)
        write(session, gen, world)
        session.commit()
        check_invariants(session)

    log.info("Đã nạp xong lần chạy %s.", SIMULATION_ID)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
