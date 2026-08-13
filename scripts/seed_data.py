#!/usr/bin/env python3
"""Sinh dữ liệu mẫu cho FIN-07.

Mục đích: một máy vừa `git clone` xong, chạy `docker compose up`, là có ngay
một hệ thống có cảnh báo để xem, có vụ việc để mở, có hồ sơ chờ duyệt. Không
phải chờ ai gửi file dump qua chat.

Phạm vi và giới hạn — đọc trước khi dùng:

  * Đây là fixture demo, KHÔNG phải dataset đánh giá. Việc nạp IBM LI-Small
    (7 triệu giao dịch, tỷ lệ rửa tiền ~0,05%) là hạng mục của Hiển ở Sprint 1
    theo FIN-07-DAT-001 mục 3. Tỷ lệ nhãn trong file này được đặt cao hơn thực
    tế để mỗi màn hình đều có dữ liệu nhìn thấy được.
  * Dữ liệu hoàn toàn tổng hợp. Không có khách hàng thật, không có tên thật
    trong danh sách trừng phạt — ARC-001 mục 5.4.
  * Tái lập được (ND5): cùng SEED_VALUE cho ra cùng dữ liệu, kể cả mốc thời
    gian. Kiểm chứng bằng `python scripts/seed_data.py --verify`, chạy hai lần
    phải in ra cùng một vân tay.

Cách dùng:
    python scripts/seed_data.py            # nạp nếu cơ sở dữ liệu còn rỗng
    python scripts/seed_data.py --force    # xoá sạch rồi nạp lại
    python scripts/seed_data.py --verify   # in vân tay nội dung, không ghi gì
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Chạy `python scripts/seed_data.py` thì sys.path[0] là thư mục scripts/, chứ
# không phải gốc repo, nên `import src...` hỏng. Image Docker đặt PYTHONPATH
# nên không gặp; người chạy tay ngoài Docker thì gặp ngay. Tự thêm gốc repo
# vào đây để script chạy được từ mọi chỗ.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.db.session import get_session  # noqa: E402

logger = logging.getLogger("fin07.seed")

# Mốc thời gian cố định, không dùng đồng hồ máy: đổi ngày chạy không được
# đổi dữ liệu (ND5).
ANCHOR = datetime(2026, 7, 28, 0, 0, 0, tzinfo=UTC)

# Ngưỡng báo cáo giao dịch giá trị lớn, đơn vị USD như dataset IBM.
REPORTING_THRESHOLD = 10_000.0

BANKS = ["001", "012", "070", "202", "310"]
CHANNELS = ["ACH", "Wire", "Credit Card", "Cash", "Cheque"]
COUNTRIES = ["VN", "VN", "VN", "VN", "SG", "HK", "KH", "US"]

PROTOTYPES = [
    # (mã, tỷ lệ, kiểu khách hàng, doanh số trung vị tháng, số đối tác)
    ("salaried", 0.60, "individual", 3_500.0, (3, 8)),
    ("household_business", 0.25, "individual", 18_000.0, (8, 25)),
    ("enterprise", 0.13, "organisation", 120_000.0, (20, 60)),
    ("shell_entity", 0.02, "organisation", 90_000.0, (30, 80)),
]

OCCUPATIONS = {
    "salaried": ["Nhân viên văn phòng", "Giáo viên", "Kỹ sư", "Công nhân", "Điều dưỡng"],
    "household_business": ["Hộ kinh doanh tạp hoá", "Bán hàng online", "Chủ quán ăn", "Thợ xây"],
    "enterprise": ["Công ty thương mại", "Công ty logistics", "Công ty xây dựng"],
    "shell_entity": ["Công ty tư vấn", "Công ty đầu tư"],
}

INCOME_BANDS = ["<10tr", "10-30tr", "30-100tr", "100-500tr", ">500tr"]

# Kho tên dùng cho danh sách trừng phạt và cho nhóm "gần giống nhưng vô can".
SURNAMES = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Đặng", "Bùi"]
MIDDLE_NAMES = ["Văn", "Thị", "Hữu", "Đức", "Minh", "Quang", "Thanh", "Ngọc"]
GIVEN_NAMES = ["An", "Bình", "Cường", "Dũng", "Hà", "Hùng", "Lan", "Mai", "Nam", "Sơn", "Tuấn", "Yến"]

TYPOLOGY_TITLES = {
    "T01": "Chia nhỏ giao dịch dưới ngưỡng báo cáo",
    "T02": "Tài khoản trung chuyển trong mạng lưới",
    "T03": "Giao dịch vòng quay lại chủ thể ban đầu",
    "T04": "Gom vào và toả ra bất thường",
    "T05": "Luân chuyển tốc độ cao",
    "T10": "Dòng tiền không tương xứng hồ sơ khách hàng",
}


def strip_accents(value: str) -> str:
    """Bỏ dấu, chuẩn hoá hoa thường — bước đầu của chuẩn hoá tên (DAT-001 mục 7.2)."""
    decomposed = unicodedata.normalize("NFD", value.replace("Đ", "D").replace("đ", "d"))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").lower().strip()


class SeedBuilder:
    """Dựng toàn bộ tập dữ liệu trong bộ nhớ trước, ghi xuống sau.

    Tách hai pha để `--verify` tính được vân tay mà không cần chạm cơ sở dữ liệu.
    """

    def __init__(self, seed: int, customers: int, days: int) -> None:
        self.rng = random.Random(seed)
        self.n_customers = customers
        self.days = days
        self.start = ANCHOR - timedelta(days=days)

        self.customers: list[dict[str, Any]] = []
        self.accounts: list[dict[str, Any]] = []
        self.transactions: list[dict[str, Any]] = []
        self.laundering_tx: list[int] = []
        self.typology_tx: list[tuple[int, str]] = []
        self.profile_mismatch: list[dict[str, Any]] = []
        self.watchlist_versions: list[dict[str, Any]] = []
        self.watchlist_entries: list[dict[str, Any]] = []
        self.watchlist_matches: list[dict[str, Any]] = []
        self.screening_results: list[dict[str, Any]] = []
        self.cases: list[dict[str, Any]] = []
        self.alerts: list[dict[str, Any]] = []
        self.alert_reasons: list[dict[str, Any]] = []
        self.evidence: list[dict[str, Any]] = []
        self.sar_drafts: list[dict[str, Any]] = []
        self.sar_statements: list[dict[str, Any]] = []
        self.statement_evidence: list[dict[str, Any]] = []
        self.approvals: list[dict[str, Any]] = []
        self.audit_log: list[dict[str, Any]] = []

    # -- tiện ích ------------------------------------------------------

    def _moment(self, day_offset: float) -> datetime:
        return self.start + timedelta(days=day_offset)

    def _split_for(self, moment: datetime) -> str:
        """Chia 60/20/20 theo thời gian, không chia ngẫu nhiên (ND2)."""
        elapsed = (moment - self.start).total_seconds() / (self.days * 86400)
        if elapsed < 0.60:
            return "train"
        if elapsed < 0.80:
            return "validation"
        return "test"

    def _add_tx(
        self,
        src: str,
        dst: str,
        amount: float,
        moment: datetime,
        *,
        channel: str | None = None,
        remarks: str = "",
        laundering: bool = False,
        typology: str | None = None,
    ) -> int:
        tx_id = len(self.transactions) + 1
        amount = round(amount, 2)
        self.transactions.append(
            {
                "transaction_id": tx_id,
                "occurred_at": moment,
                "from_account_key": src,
                "to_account_key": dst,
                "amount": amount,
                "currency": "USD",
                "amount_received": amount,
                "receiving_currency": "USD",
                "channel": channel or self.rng.choice(CHANNELS),
                "remarks": remarks,
                "dataset_split": self._split_for(moment),
            }
        )
        if laundering:
            self.laundering_tx.append(tx_id)
        if typology:
            self.typology_tx.append((tx_id, typology))
        return tx_id

    # -- pha 1: khách hàng và tài khoản --------------------------------

    def build_parties(self) -> None:
        # Các nhóm nhỏ được cấp số lượng tối thiểu trước, phần dư dồn về nhóm
        # cá nhân hưởng lương. Làm ngược lại thì với tệp nhỏ nhóm pháp nhân vỏ
        # (~2%) bị làm tròn về 0 và không cài được kịch bản nào.
        allocation: list[str] = []
        for name, ratio, *_ in PROTOTYPES[1:]:
            allocation.extend([name] * max(2, round(self.n_customers * ratio)))
        allocation = ["salaried"] * max(1, self.n_customers - len(allocation)) + allocation
        allocation = allocation[: self.n_customers]

        spec = {p[0]: p for p in PROTOTYPES}

        for idx, prototype in enumerate(allocation, start=1):
            _, _, customer_type, median_volume, _partners = spec[prototype]
            volume = round(median_volume * self.rng.uniform(0.7, 1.4), 2)
            onboarding = (self.start - timedelta(days=self.rng.randint(30, 1500))).date()
            if prototype == "shell_entity":
                onboarding = (self.start - timedelta(days=self.rng.randint(5, 60))).date()

            customer_id = f"CUS-{idx:05d}"
            self.customers.append(
                {
                    "customer_id": customer_id,
                    "customer_type": customer_type,
                    "prototype": prototype,
                    "occupation": self.rng.choice(OCCUPATIONS[prototype]),
                    "declared_income_band": self._income_band(volume),
                    "expected_monthly_volume": volume,
                    "registered_country": self.rng.choice(COUNTRIES),
                    "onboarding_date": onboarding,
                    # Suy ra từ nguyên mẫu và quốc gia, không từ nhãn rửa tiền (ND1).
                    "risk_rating": self._risk_rating(prototype),
                    "created_at": self.start,
                }
            )

            for acc_no in range(1, self.rng.choice([1, 1, 1, 2]) + 1):
                bank = self.rng.choice(BANKS)
                number = f"{idx:05d}{acc_no}"
                self.accounts.append(
                    {
                        # Ghép mã ngân hàng vào khoá: không ghép thì hai tài khoản
                        # khác nhau ở hai ngân hàng bị coi là một (DAT-001 mục 4.1).
                        "account_key": f"{bank}:{number}",
                        "customer_id": customer_id,
                        "bank_code": bank,
                        "account_number": number,
                        "opened_at": onboarding,
                        "status": "active",
                        "created_at": self.start,
                    }
                )

    @staticmethod
    def _income_band(volume: float) -> str:
        for ceiling, band in (
            (5_000, INCOME_BANDS[0]),
            (20_000, INCOME_BANDS[1]),
            (60_000, INCOME_BANDS[2]),
            (200_000, INCOME_BANDS[3]),
        ):
            if volume < ceiling:
                return band
        return INCOME_BANDS[4]

    def _risk_rating(self, prototype: str) -> str:
        if prototype == "shell_entity":
            return "high"
        if prototype == "enterprise":
            return self.rng.choice(["medium", "medium", "high"])
        return self.rng.choice(["low", "low", "low", "medium"])

    def _accounts_of(self, prototype: str) -> list[str]:
        wanted = {c["customer_id"] for c in self.customers if c["prototype"] == prototype}
        return [a["account_key"] for a in self.accounts if a["customer_id"] in wanted]

    # -- pha 2: giao dịch nền -----------------------------------------

    def build_background_traffic(self) -> None:
        """Lưu lượng hợp pháp — phần lớn dữ liệu, và là thứ quyết định
        cảnh báo giả nhiều hay ít."""
        by_customer = {c["customer_id"]: c for c in self.customers}
        keys = [a["account_key"] for a in self.accounts]

        for account in self.accounts:
            customer = by_customer[account["customer_id"]]
            monthly = float(customer["expected_monthly_volume"])
            n_tx = max(4, int(self.days / 30 * self.rng.randint(6, 22)))
            partners = self.rng.sample(
                [k for k in keys if k != account["account_key"]], k=min(len(keys) - 1, self.rng.randint(3, 12))
            )

            for _ in range(n_tx):
                offset = self.rng.uniform(0, self.days)
                # Giờ giao dịch lệch về giờ hành chính, chừa đuôi ngoài giờ.
                hour = self.rng.choice([8, 9, 10, 11, 13, 14, 15, 16, 17, 20, 22])
                moment = self._moment(offset).replace(hour=hour, minute=self.rng.randrange(60), second=0, microsecond=0)
                amount = max(12.0, self.rng.gauss(monthly / 12, monthly / 30))
                counterparty = self.rng.choice(partners)
                if self.rng.random() < 0.5:
                    self._add_tx(account["account_key"], counterparty, amount, moment)
                else:
                    self._add_tx(counterparty, account["account_key"], amount, moment)

    # -- pha 3: cài kịch bản rửa tiền ----------------------------------

    def plant_typologies(self) -> list[dict[str, Any]]:
        """Cài các kịch bản T01–T05 và T10, trả về danh sách chủ thể đáng ngờ."""
        subjects: list[dict[str, Any]] = []
        subjects.append(self._plant_structuring())
        subjects.append(self._plant_mule_network())
        subjects.append(self._plant_cycle())
        subjects.append(self._plant_fan_in_out())
        subjects.append(self._plant_profile_mismatch())
        return subjects

    def _plant_structuring(self) -> dict[str, Any]:
        """T01 — nhiều khoản nằm sát dưới ngưỡng, cộng dồn thì vượt."""
        subject = self._accounts_of("household_business")[0]
        sink = self._accounts_of("enterprise")[0]
        base_day = self.days * 0.72
        for i in range(11):
            amount = REPORTING_THRESHOLD - self.rng.uniform(120, 850)
            moment = self._moment(base_day + i * 0.18).replace(minute=self.rng.randrange(60), second=0, microsecond=0)
            self._add_tx(
                subject,
                sink,
                amount,
                moment,
                channel="Cash",
                remarks="thanh toan hang",
                laundering=True,
                typology="T01",
            )
        return {"account_key": subject, "typology": "T01", "score": 78.5}

    def _plant_mule_network(self) -> dict[str, Any]:
        """T02 + T05 — tiền chỉ đi qua, số dư cuối ngày gần bằng không."""
        salaried = self._accounts_of("salaried")
        mules = salaried[2:8]
        source = self._accounts_of("enterprise")[1]
        collector = self._accounts_of("shell_entity")[0]
        base_day = self.days * 0.80

        for i, mule in enumerate(mules):
            amount = self.rng.uniform(7_500, 9_400)
            arrive = self._moment(base_day + i * 0.05).replace(minute=self.rng.randrange(60), second=0, microsecond=0)
            # Thời gian lưu tiền tính bằng phút — dấu vết của T05.
            leave = arrive + timedelta(minutes=self.rng.randint(3, 26))
            self._add_tx(source, mule, amount, arrive, channel="Wire", laundering=True, typology="T02")
            self._add_tx(mule, collector, amount * 0.985, leave, channel="Wire", laundering=True, typology="T05")
        return {"account_key": collector, "typology": "T02", "score": 91.0}

    def _plant_cycle(self) -> dict[str, Any]:
        """T03 — chu trình có hướng dài 4 bước quay về điểm xuất phát."""
        ring = self._accounts_of("household_business")[3:7]
        if len(ring) < 4:
            ring = [a["account_key"] for a in self.accounts[:4]]
        base_day = self.days * 0.86
        amount = 46_000.0
        for i in range(len(ring)):
            src = ring[i]
            dst = ring[(i + 1) % len(ring)]
            moment = self._moment(base_day + i * 0.12).replace(minute=self.rng.randrange(60), second=0, microsecond=0)
            self._add_tx(src, dst, amount * (0.99**i), moment, channel="Wire", laundering=True, typology="T03")
        return {"account_key": ring[0], "typology": "T03", "score": 84.0}

    def _plant_fan_in_out(self) -> dict[str, Any]:
        """T04 — nhiều nguồn nhỏ đổ về một tài khoản gom rồi toả ra."""
        hub = self._accounts_of("shell_entity")[-1]
        salaried = self._accounts_of("salaried")
        sources = salaried[10:22]
        sinks = salaried[22:30] or salaried[:8]
        base_day = self.days * 0.90

        collected = 0.0
        for i, src in enumerate(sources):
            amount = self.rng.uniform(2_100, 4_800)
            collected += amount
            moment = self._moment(base_day + i * 0.02).replace(minute=self.rng.randrange(60), second=0, microsecond=0)
            self._add_tx(src, hub, amount, moment, laundering=True, typology="T04")
        for i, dst in enumerate(sinks):
            amount = collected / len(sinks) * 0.97
            moment = self._moment(base_day + 0.5 + i * 0.02).replace(
                minute=self.rng.randrange(60), second=0, microsecond=0
            )
            self._add_tx(hub, dst, amount, moment, laundering=True, typology="T04")
        return {"account_key": hub, "typology": "T04", "score": 88.5}

    def _plant_profile_mismatch(self) -> dict[str, Any]:
        """T10 — tiêm lệch hồ sơ có kiểm soát (DAT-001 mục 5.4).

        Nhãn này độc lập với nhãn rửa tiền: khoảng một phần tư số tài khoản bị
        tiêm trùng với nhãn rửa tiền, phần còn lại là dương tính giả hợp pháp —
        chính là loại ca hệ thống phải học cách không báo động quá mức.
        """
        salaried = self._accounts_of("salaried")
        picked = salaried[30:34] or salaried[:4]
        laundering_accounts = {
            t["from_account_key"] for t in self.transactions if t["transaction_id"] in set(self.laundering_tx)
        }

        base_day = self.days * 0.55
        for i, account in enumerate(picked):
            self.profile_mismatch.append(
                {
                    "account_key": account,
                    "reason": "Hành vi theo nguyên mẫu doanh nghiệp nhưng khai là cá nhân hưởng lương, khoảng thu nhập thấp nhất",
                }
            )
            # Dòng tiền quy mô doanh nghiệp trên một hồ sơ cá nhân.
            partner = self._accounts_of("enterprise")[i % 2]
            is_also_laundering = account in laundering_accounts
            for j in range(6):
                moment = self._moment(base_day + i * 0.3 + j * 0.4).replace(
                    minute=self.rng.randrange(60), second=0, microsecond=0
                )
                self._add_tx(
                    account,
                    partner,
                    self.rng.uniform(28_000, 65_000),
                    moment,
                    channel="Wire",
                    laundering=is_also_laundering,
                    typology="T10",
                )
        return {"account_key": picked[0], "typology": "T10", "score": 66.0}

    # -- pha 4: danh sách trừng phạt và đối chiếu ----------------------

    def build_watchlists(self) -> None:
        """Ba phiên bản danh sách để diễn tập kiểm toán (DAT-001 mục 7.1).

        Tên trong đây là tên sinh, không phải người thật. Điểm quan trọng của
        khối này là nhóm `near_miss`: không có nhóm gần giống thì không đo được
        việc giảm khớp sai, vì không tồn tại khớp sai nào để giảm (P07).
        """
        for offset, (source, count) in enumerate(
            [("OpenSanctions default", 24), ("OpenSanctions default", 27), ("OpenSanctions default + OFAC SDN", 30)]
        ):
            loaded = self.start + timedelta(days=offset * (self.days / 3))
            version_id = f"WL-{loaded.date().isoformat().replace('-', '')}"
            self.watchlist_versions.append(
                {
                    "watchlist_version_id": version_id,
                    "source": source,
                    "loaded_at": loaded,
                    "entry_count": count,
                    "checksum": hashlib.sha256(f"{version_id}:{count}".encode()).hexdigest(),
                }
            )

        latest = self.watchlist_versions[-1]
        for i in range(latest["entry_count"]):
            surname = self.rng.choice(SURNAMES)
            middle = self.rng.choice(MIDDLE_NAMES)
            given = self.rng.choice(GIVEN_NAMES)
            full = f"{surname} {middle} {given}"
            self.watchlist_entries.append(
                {
                    "list_entry_id": f"WLE-{i + 1:04d}",
                    "watchlist_version_id": latest["watchlist_version_id"],
                    "full_name": full,
                    "normalized_name": strip_accents(full),
                    # Bí danh tách và lập chỉ mục riêng (DAT-001 mục 7.2).
                    "aliases": [strip_accents(f"{given} {surname}"), f"{surname} {given}"],
                    "entity_type": "person",
                    "country": self.rng.choice(["VN", "KH", "SG"]),
                    "list_type": "sanction" if i % 3 else "pep",
                }
            )

        # Ba nhóm ground truth (DAT-001 mục 6).
        keys = [a["account_key"] for a in self.accounts]
        exact_accounts = keys[:1]
        # Tỷ lệ mục tiêu là ~2% (DAT-001 mục 6), nhưng trên tệp demo vài chục
        # tài khoản thì 2% ra một dòng, và một dòng thì không đo được tỷ lệ
        # khớp sai. Sàn ba dòng để nhóm này có ý nghĩa khi xem trên màn hình.
        near_miss_accounts = keys[5 : 5 + max(3, round(len(keys) * 0.02))]

        for account in exact_accounts:
            entry = self.watchlist_entries[0]
            self.watchlist_matches.append(
                {"account_key": account, "list_entry_id": entry["list_entry_id"], "match_type": "exact"}
            )
            self.screening_results.append(
                {
                    "screening_id": f"SCR-{len(self.screening_results) + 1:05d}",
                    "case_id": None,
                    "account_key": account,
                    "list_entry_id": entry["list_entry_id"],
                    "watchlist_version_id": latest["watchlist_version_id"],
                    "score": 0.9820,
                    "verdict": "strong_match",
                    "screened_at": ANCHOR - timedelta(days=1),
                }
            )

        for i, account in enumerate(near_miss_accounts):
            entry = self.watchlist_entries[(i + 3) % len(self.watchlist_entries)]
            self.watchlist_matches.append(
                {"account_key": account, "list_entry_id": entry["list_entry_id"], "match_type": "near_miss"}
            )
            self.screening_results.append(
                {
                    "screening_id": f"SCR-{len(self.screening_results) + 1:05d}",
                    "case_id": None,
                    "account_key": account,
                    "list_entry_id": entry["list_entry_id"],
                    "watchlist_version_id": latest["watchlist_version_id"],
                    "score": round(self.rng.uniform(0.71, 0.86), 4),
                    # Gần giống nhưng vô can: phải KHÔNG báo ở mức khớp mạnh.
                    "verdict": "needs_review",
                    "screened_at": ANCHOR - timedelta(days=1),
                }
            )

    # -- pha 5: cảnh báo, vụ việc, hồ sơ -------------------------------

    def build_cases(self, subjects: list[dict[str, Any]]) -> None:
        priority_of = {90: "critical", 80: "high", 60: "medium"}

        for idx, subject in enumerate(subjects, start=1):
            case_id = f"CASE-2026-{idx:04d}"
            score = subject["score"]
            priority = next((v for k, v in sorted(priority_of.items(), reverse=True) if score >= k), "low")
            created = ANCHOR - timedelta(days=len(subjects) - idx, hours=3)

            self.cases.append(
                {
                    "case_id": case_id,
                    "subject_account_key": subject["account_key"],
                    "title": f"{TYPOLOGY_TITLES[subject['typology']]} — {subject['account_key']}",
                    # Chỉ vụ việc đầu tiên được đẩy tới cuối luồng; các vụ còn
                    # lại nằm ở hàng đợi để có cái mà thao tác khi demo.
                    "state": "ChoNguoiPheDuyet" if idx == 1 else "TiepNhanCanhBao",
                    "risk_score": score,
                    "priority": priority,
                    "assigned_to": "analyst.tin" if idx % 2 else "analyst.hung",
                    "created_at": created,
                    "updated_at": created + timedelta(hours=2),
                }
            )
            self.audit_log.append(
                {
                    "case_id": case_id,
                    "event_type": "alert_raised",
                    "actor": "detection-service",
                    "actor_role": "system",
                    "payload": json.dumps({"typology": subject["typology"], "risk_score": score}),
                    "occurred_at": created,
                }
            )

            # Mỗi cảnh báo kèm tối thiểu ba yếu tố đóng góp có giá trị số (NT7).
            for detector, weight in (("rule", 0.4), ("ml", 0.35), ("graph", 0.25)):
                alert_id = f"ALT-{idx:03d}-{detector}"
                self.alerts.append(
                    {
                        "alert_id": alert_id,
                        "account_key": subject["account_key"],
                        "transaction_id": None,
                        "typology_code": subject["typology"],
                        "detector": detector,
                        "risk_score": round(score * self.rng.uniform(0.9, 1.05), 2) if score * 1.05 < 100 else score,
                        "status": "grouped",
                        "case_id": case_id,
                        "created_at": created,
                    }
                )
                for factor_code, factor_label, contribution in self._factors(subject["typology"], detector):
                    self.alert_reasons.append(
                        {
                            "alert_id": alert_id,
                            "factor_code": factor_code,
                            "factor_label": factor_label,
                            "contribution": contribution,
                            "weight": weight,
                        }
                    )

        self._build_worked_case(self.cases[0])

    def _factors(self, typology: str, detector: str) -> list[tuple[str, str, float]]:
        table = {
            "T01": [
                ("amount_below_threshold_ratio", "Tỷ lệ giao dịch nằm sát dưới ngưỡng báo cáo", 34.0),
                ("amount_stddev", "Độ lệch chuẩn số tiền rất nhỏ", 21.5),
                ("window_sum_over_threshold", "Tổng cộng dồn 7 ngày vượt ngưỡng", 23.0),
            ],
            "T02": [
                ("pass_through_ratio", "Tỷ lệ tiền ra trên tiền vào xấp xỉ một", 38.0),
                ("dwell_time_minutes", "Thời gian lưu tiền trung vị tính bằng phút", 29.0),
                ("new_counterparty_ratio", "Tỷ lệ đối tác mới trong tháng", 24.0),
            ],
            "T03": [
                ("cycle_length", "Thuộc chu trình có hướng dài 4 bước", 33.0),
                ("cycle_value", "Tổng giá trị chu trình", 27.5),
                ("step_latency", "Độ trễ giữa các bước ngắn và đều", 23.5),
            ],
            "T04": [
                ("in_degree_spike", "Bậc vào tăng đột biến trong 24 giờ", 36.0),
                ("out_degree_spike", "Bậc ra tăng đột biến ngay sau đó", 31.0),
                ("balance_end_of_day", "Số dư cuối ngày gần bằng không", 21.5),
            ],
            "T10": [
                ("volume_over_declared", "Doanh số thực tế trên doanh số khai báo", 30.0),
                ("prototype_deviation", "Lệch so với nguyên mẫu hành vi", 22.0),
                ("counterparty_profile", "Đối tác thuộc nhóm doanh nghiệp", 18.0),
            ],
        }
        factors = table[typology]
        shift = {"rule": 1.0, "ml": 0.92, "graph": 1.06}[detector]
        return [(code, label, round(value * shift, 2)) for code, label, value in factors]

    def _build_worked_case(self, case: dict[str, Any]) -> None:
        """Một vụ việc đi hết luồng: bằng chứng, hồ sơ, chờ duyệt.

        Mỗi câu trong hồ sơ đều trỏ vào bằng chứng cụ thể (NT1). View
        `uncited_statement` phải rỗng sau khi seed xong.
        """
        case_id = case["case_id"]
        base = case["created_at"] + timedelta(hours=1)
        subject = case["subject_account_key"]

        subject_tx = [t for t in self.transactions if t["from_account_key"] == subject][:3]
        for i, tx in enumerate(subject_tx, start=1):
            payload = {
                "transaction_id": tx["transaction_id"],
                "occurred_at": tx["occurred_at"].isoformat(),
                "amount": tx["amount"],
                "currency": tx["currency"],
                "from_account_key": tx["from_account_key"],
                "to_account_key": tx["to_account_key"],
            }
            body = json.dumps(payload, sort_keys=True)
            self.evidence.append(
                {
                    "evidence_id": f"EV-{case_id}-{i:03d}",
                    "case_id": case_id,
                    "source_table": "transaction",
                    "source_ref": str(tx["transaction_id"]),
                    "payload": body,
                    "retrieved_at": base,
                    "evidence_hash": hashlib.sha256(body.encode()).hexdigest(),
                }
            )

        draft_id = f"SAR-{case_id}"
        self.sar_drafts.append(
            {
                "sar_draft_id": draft_id,
                "case_id": case_id,
                "version": 1,
                "status": "submitted_for_approval",
                "created_at": base + timedelta(minutes=40),
            }
        )

        statements = [
            "Tài khoản chủ thể thực hiện 11 giao dịch tiền mặt trong 48 giờ, mỗi giao dịch nằm dưới ngưỡng báo cáo dưới 900 đơn vị.",
            "Tổng giá trị cộng dồn của nhóm giao dịch nêu trên vượt ngưỡng báo cáo giao dịch giá trị lớn.",
            "Độ lệch chuẩn số tiền giữa các giao dịch nhỏ bất thường so với lịch sử 90 ngày của chính tài khoản này.",
        ]
        for ordinal, body in enumerate(statements, start=1):
            statement_id = f"ST-{case_id}-{ordinal:03d}"
            self.sar_statements.append(
                {"statement_id": statement_id, "sar_draft_id": draft_id, "ordinal": ordinal, "body": body}
            )
            # Một câu dựa trên nhiều bằng chứng, một bằng chứng phục vụ nhiều
            # câu — quan hệ nhiều–nhiều là bắt buộc (ARC-001 mục 3.6).
            for ev in self.evidence[: ordinal + 1]:
                self.statement_evidence.append({"statement_id": statement_id, "evidence_id": ev["evidence_id"]})

        self.approvals.append(
            {
                "approval_id": f"APR-{case_id}",
                "case_id": case_id,
                "sar_draft_id": draft_id,
                "decision": "pending",
                "decided_by": None,
                "reason": None,
                "requested_at": base + timedelta(minutes=55),
                "decided_at": None,
            }
        )

        for offset, (event, actor, role, payload) in enumerate(
            [
                ("agent_query", "investigation-agent", "agent", {"tool": "get_transactions", "window_days": 30}),
                (
                    "case_state_changed",
                    "investigation-agent",
                    "agent",
                    {"from": "TiepNhanCanhBao", "to": "TruyHoiBangChung"},
                ),
                (
                    "case_state_changed",
                    "investigation-agent",
                    "agent",
                    {"from": "KiemChungBangChung", "to": "ChoNguoiPheDuyet"},
                ),
                ("submitted_for_approval", "analyst.tin", "analyst", {"sar_draft_id": draft_id}),
            ]
        ):
            self.audit_log.append(
                {
                    "case_id": case_id,
                    "event_type": event,
                    "actor": actor,
                    "actor_role": role,
                    "payload": json.dumps(payload),
                    "occurred_at": base + timedelta(minutes=10 * offset),
                }
            )

    # -- dựng toàn bộ --------------------------------------------------

    def build(self) -> SeedBuilder:
        self.build_parties()
        self.build_background_traffic()
        subjects = self.plant_typologies()
        self.build_watchlists()
        self.build_cases(subjects)
        return self

    def fingerprint(self) -> str:
        """Vân tay nội dung — hai lần chạy cùng seed phải cho cùng giá trị."""
        digest = hashlib.sha256()
        for name in (
            "customers",
            "accounts",
            "transactions",
            "laundering_tx",
            "typology_tx",
            "profile_mismatch",
            "watchlist_versions",
            "watchlist_entries",
            "watchlist_matches",
            "screening_results",
            "cases",
            "alerts",
            "alert_reasons",
            "evidence",
            "sar_drafts",
            "sar_statements",
            "statement_evidence",
            "approvals",
            "audit_log",
        ):
            digest.update(name.encode())
            digest.update(repr(getattr(self, name)).encode())
        return digest.hexdigest()

    def summary(self) -> dict[str, int]:
        return {
            "customer": len(self.customers),
            "account": len(self.accounts),
            "transaction": len(self.transactions),
            "label_laundering": len(self.laundering_tx),
            "label_profile_mismatch": len(self.profile_mismatch),
            "label_watchlist_match": len(self.watchlist_matches),
            "watchlist_version": len(self.watchlist_versions),
            "watchlist_entry": len(self.watchlist_entries),
            "screening_result": len(self.screening_results),
            "aml_case": len(self.cases),
            "alert": len(self.alerts),
            "alert_reason": len(self.alert_reasons),
            "evidence": len(self.evidence),
            "sar_statement": len(self.sar_statements),
            "approval": len(self.approvals),
            "audit_log": len(self.audit_log),
        }


# -- ghi xuống cơ sở dữ liệu ------------------------------------------

TABLES_IN_WIPE_ORDER = [
    "sar_statement_evidence",
    "sar_statement",
    "sar_draft",
    "approval",
    "audit_log",
    # Migrations 006-009 added the investigation runtime and the Behaviour batch
    # tables. Leaving them out made --force a half-wipe: detection rows and
    # investigations survived pointing at accounts and transactions that had
    # just been deleted, so a reseeded database still served the previous
    # batch's alerts. Children first; `evidence` below is held by
    # investigation_evidence with ON DELETE RESTRICT.
    "case_explanation",
    "investigation_validation",
    "investigation_agent_run",
    "investigation_tool_call",
    "investigation_trace",
    "investigation_evidence",
    "investigation",
    "detection_result",
    "behavior_feature_snapshot",
    "behavior_batch",
    "evidence",
    "screening_result",
    "alert_reason",
    "alert",
    "aml_case",
    "label.label_watchlist_match",
    "label.label_profile_mismatch",
    "label.label_typology",
    "label.label_laundering",
    "watchlist_entry",
    "watchlist_version",
    "transaction",
    "account",
    "customer",
]


# Những gì db/init/ phải để lại. Danh sách này ngắn có chủ ý: nó không thay
# cho việc đọc lược đồ, nó chỉ phát hiện một cơ sở dữ liệu khởi tạo dở dang.
REQUIRED_SCHEMAS = ["public", "label", "agent"]
REQUIRED_TABLES = [
    "customer",
    "account",
    "transaction",
    "alert",
    "alert_reason",
    "aml_case",
    "evidence",
    "sar_draft",
    "sar_statement",
    "sar_statement_evidence",
    "approval",
    "audit_log",
    "watchlist_version",
    "watchlist_entry",
    "screening_result",
    "app_user",
    "app_session",
    "system_setting",
]
REQUIRED_ROLES = ["fin07_agent"]


def check_schema(session: Session) -> None:
    """Dừng sớm nếu lược đồ chưa được dựng đủ.

    Một script trong db/init/ hỏng có thể để lại cơ sở dữ liệu khởi tạo dở
    dang mà container postgres vẫn báo xanh — script khởi tạo chỉ chạy khi
    volume còn rỗng, nên lần khởi động sau nó không chạy lại và cũng không
    kêu ca gì. Dịch vụ seed chạy trước api và worker, và api với worker chỉ
    khởi động khi seed thoát với mã 0. Đặt kiểm tra ở đây thì hỏng lược đồ
    biến thành "cả stack không lên", chứ không phải "mọi thứ xanh, lỗi 500
    lúc bấm vào".
    """
    missing: list[str] = []

    found_schemas = set(session.execute(text("SELECT nspname FROM pg_namespace")).scalars().all())
    missing += [f"schema {s}" for s in REQUIRED_SCHEMAS if s not in found_schemas]

    found_tables = set(
        session.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars().all()
    )
    missing += [f"bảng {t}" for t in REQUIRED_TABLES if t not in found_tables]

    found_roles = set(session.execute(text("SELECT rolname FROM pg_roles")).scalars().all())
    missing += [f"vai trò {r}" for r in REQUIRED_ROLES if r not in found_roles]

    if missing:
        logger.error("Lược đồ chưa đầy đủ, thiếu: %s", ", ".join(missing))
        logger.error("Cơ sở dữ liệu đã khởi tạo dở dang. Dựng lại từ đầu: make db-reset")
        raise SystemExit(1)


def is_empty(session: Session) -> bool:
    return session.execute(text("SELECT count(*) FROM customer")).scalar_one() == 0


def wipe(session: Session) -> None:
    """Xoá sạch dữ liệu nghiệp vụ.

    audit_log, evidence và approval bị trigger chặn xoá (QD6). Đường duy nhất
    đi qua là tắt trigger trong đúng transaction này — chỉ dùng để dựng lại môi
    trường phát triển, và bị chặn khi APP_ENV=production.
    """
    if get_settings().app_env == "production":
        raise SystemExit("Từ chối xoá dữ liệu khi APP_ENV=production")
    session.execute(text("SET LOCAL session_replication_role = 'replica'"))
    for table in TABLES_IN_WIPE_ORDER:
        session.execute(text(f"DELETE FROM {table}"))
    session.execute(text("ALTER SEQUENCE transaction_transaction_id_seq RESTART WITH 1"))


def _insert(session: Session, sql: str, rows: list[dict[str, Any]]) -> None:
    if rows:
        session.execute(text(sql), rows)


def write(session: Session, data: SeedBuilder) -> None:
    _insert(
        session,
        """INSERT INTO customer (customer_id, customer_type, prototype, occupation, declared_income_band,
                                 expected_monthly_volume, registered_country, onboarding_date, risk_rating, created_at)
           VALUES (:customer_id, :customer_type, :prototype, :occupation, :declared_income_band,
                   :expected_monthly_volume, :registered_country, :onboarding_date, :risk_rating, :created_at)""",
        data.customers,
    )
    _insert(
        session,
        """INSERT INTO account (account_key, customer_id, bank_code, account_number, opened_at, status, created_at)
           VALUES (:account_key, :customer_id, :bank_code, :account_number, :opened_at, :status, :created_at)""",
        data.accounts,
    )
    _insert(
        session,
        """INSERT INTO transaction (transaction_id, occurred_at, from_account_key, to_account_key, amount, currency,
                                    amount_received, receiving_currency, channel, remarks, dataset_split)
           VALUES (:transaction_id, :occurred_at, :from_account_key, :to_account_key, :amount, :currency,
                   :amount_received, :receiving_currency, :channel, :remarks, :dataset_split)""",
        data.transactions,
    )
    session.execute(
        text("SELECT setval('transaction_transaction_id_seq', (SELECT max(transaction_id) FROM transaction))")
    )

    laundering_set = set(data.laundering_tx)
    _insert(
        session,
        "INSERT INTO label.label_laundering (transaction_id, is_laundering) VALUES (:transaction_id, :is_laundering)",
        [
            {"transaction_id": t["transaction_id"], "is_laundering": t["transaction_id"] in laundering_set}
            for t in data.transactions
        ],
    )
    _insert(
        session,
        "INSERT INTO label.label_typology (transaction_id, typology_code) VALUES (:transaction_id, :typology_code)",
        [{"transaction_id": tx, "typology_code": code} for tx, code in sorted(set(data.typology_tx))],
    )
    _insert(
        session,
        "INSERT INTO label.label_profile_mismatch (account_key, reason) VALUES (:account_key, :reason)",
        data.profile_mismatch,
    )
    _insert(
        session,
        """INSERT INTO watchlist_version (watchlist_version_id, source, loaded_at, entry_count, checksum)
           VALUES (:watchlist_version_id, :source, :loaded_at, :entry_count, :checksum)""",
        data.watchlist_versions,
    )
    _insert(
        session,
        """INSERT INTO watchlist_entry (list_entry_id, watchlist_version_id, full_name, normalized_name, aliases,
                                        entity_type, country, list_type)
           VALUES (:list_entry_id, :watchlist_version_id, :full_name, :normalized_name, :aliases,
                   :entity_type, :country, :list_type)""",
        data.watchlist_entries,
    )
    _insert(
        session,
        """INSERT INTO label.label_watchlist_match (account_key, list_entry_id, match_type)
           VALUES (:account_key, :list_entry_id, :match_type)""",
        data.watchlist_matches,
    )
    _insert(
        session,
        """INSERT INTO aml_case (case_id, subject_account_key, title, state, risk_score, priority, assigned_to,
                                 created_at, updated_at)
           VALUES (:case_id, :subject_account_key, :title, :state, :risk_score, :priority, :assigned_to,
                   :created_at, :updated_at)""",
        data.cases,
    )
    _insert(
        session,
        """INSERT INTO alert (alert_id, account_key, transaction_id, typology_code, detector, risk_score, status,
                              case_id, created_at)
           VALUES (:alert_id, :account_key, :transaction_id, :typology_code, :detector, :risk_score, :status,
                   :case_id, :created_at)""",
        data.alerts,
    )
    _insert(
        session,
        """INSERT INTO alert_reason (alert_id, factor_code, factor_label, contribution, weight)
           VALUES (:alert_id, :factor_code, :factor_label, :contribution, :weight)""",
        data.alert_reasons,
    )
    _insert(
        session,
        """INSERT INTO screening_result (screening_id, case_id, account_key, list_entry_id, watchlist_version_id,
                                         score, verdict, screened_at)
           VALUES (:screening_id, :case_id, :account_key, :list_entry_id, :watchlist_version_id,
                   :score, :verdict, :screened_at)""",
        data.screening_results,
    )
    _insert(
        session,
        """INSERT INTO evidence (evidence_id, case_id, source_table, source_ref, payload, retrieved_at, evidence_hash)
           VALUES (:evidence_id, :case_id, :source_table, :source_ref, CAST(:payload AS jsonb), :retrieved_at, :evidence_hash)""",
        data.evidence,
    )
    _insert(
        session,
        """INSERT INTO sar_draft (sar_draft_id, case_id, version, status, created_at)
           VALUES (:sar_draft_id, :case_id, :version, :status, :created_at)""",
        data.sar_drafts,
    )
    _insert(
        session,
        "INSERT INTO sar_statement (statement_id, sar_draft_id, ordinal, body) VALUES (:statement_id, :sar_draft_id, :ordinal, :body)",
        data.sar_statements,
    )
    _insert(
        session,
        "INSERT INTO sar_statement_evidence (statement_id, evidence_id) VALUES (:statement_id, :evidence_id)",
        data.statement_evidence,
    )
    _insert(
        session,
        """INSERT INTO approval (approval_id, case_id, sar_draft_id, decision, decided_by, reason, requested_at, decided_at)
           VALUES (:approval_id, :case_id, :sar_draft_id, :decision, :decided_by, :reason, :requested_at, :decided_at)""",
        data.approvals,
    )
    _insert(
        session,
        """INSERT INTO audit_log (case_id, event_type, actor, actor_role, payload, occurred_at)
           VALUES (:case_id, :event_type, :actor, :actor_role, CAST(:payload AS jsonb), :occurred_at)""",
        data.audit_log,
    )


def check_invariants(session: Session) -> None:
    """Kiểm tra chất lượng dữ liệu (DAT-001 mục 10). Lệch thì dừng, không cảnh báo suông."""
    failures: list[str] = []

    uncited = session.execute(text("SELECT count(*) FROM uncited_statement")).scalar_one()
    if uncited:
        failures.append(f"NT1: {uncited} câu trong hồ sơ không tham chiếu bằng chứng")

    self_loops = session.execute(
        text("SELECT count(*) FROM transaction WHERE from_account_key = to_account_key")
    ).scalar_one()
    if self_loops:
        failures.append(f"{self_loops} cạnh tự trỏ trong đồ thị giao dịch")

    thin_alerts = session.execute(
        text(
            """SELECT count(*) FROM (
                   SELECT a.alert_id FROM alert a
                   LEFT JOIN alert_reason r ON r.alert_id = a.alert_id
                   GROUP BY a.alert_id HAVING count(r.alert_reason_id) < 3
               ) t"""
        )
    ).scalar_one()
    if thin_alerts:
        failures.append(f"NT7: {thin_alerts} cảnh báo có ít hơn ba yếu tố đóng góp")

    split_overlap = session.execute(
        text(
            """SELECT count(*) FROM transaction
                WHERE dataset_split = 'test'
                  AND occurred_at <= (SELECT max(occurred_at) FROM transaction WHERE dataset_split = 'train')"""
        )
    ).scalar_one()
    if split_overlap:
        failures.append(
            f"ND2: {split_overlap} giao dịch của tập kiểm thử sớm hơn giao dịch muộn nhất của tập huấn luyện"
        )

    versions = session.execute(text("SELECT count(*) FROM watchlist_version")).scalar_one()
    if versions < 3:
        failures.append(f"DAT-001 mục 7.1: cần tối thiểu ba phiên bản danh sách, đang có {versions}")

    near_miss = session.execute(
        text("SELECT count(*) FROM label.label_watchlist_match WHERE match_type = 'near_miss'")
    ).scalar_one()
    if near_miss == 0:
        failures.append("DAT-001 mục 6: thiếu nhóm gần giống nhưng vô can — không đo được tỷ lệ khớp sai")

    if failures:
        for line in failures:
            logger.error("KIỂM TRA THẤT BẠI — %s", line)
        raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sinh dữ liệu mẫu FIN-07")
    parser.add_argument("--force", action="store_true", help="Xoá dữ liệu hiện có rồi nạp lại")
    parser.add_argument("--verify", action="store_true", help="Chỉ in vân tay nội dung, không ghi cơ sở dữ liệu")
    parser.add_argument("--seed", type=int, default=None, help="Ghi đè SEED_VALUE")
    args = parser.parse_args(argv)

    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)-8s %(message)s", stream=sys.stdout)

    seed = args.seed if args.seed is not None else settings.seed_value
    data = SeedBuilder(seed=seed, customers=settings.seed_customers, days=settings.seed_days).build()

    if args.verify:
        print(f"seed={seed}")
        print(f"fingerprint={data.fingerprint()}")
        for table, count in data.summary().items():
            print(f"  {table:24s} {count:>7d}")
        return 0

    with get_session() as session:
        check_schema(session)

        if not is_empty(session):
            if not args.force:
                logger.info("Cơ sở dữ liệu đã có dữ liệu — bỏ qua. Dùng --force để nạp lại.")
                return 0
            logger.info("Xoá dữ liệu hiện có")
            wipe(session)

        logger.info("Nạp dữ liệu mẫu, seed=%s", seed)
        write(session, data)

    with get_session() as session:
        check_invariants(session)

    for table, count in data.summary().items():
        logger.info("  %-24s %7d", table, count)
    logger.info("Xong. Vân tay: %s", data.fingerprint())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
