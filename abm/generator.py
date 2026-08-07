"""Deterministic canonical ABM-BANK world generator."""

from __future__ import annotations

import hashlib
import math
import random
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from abm.models import ReleaseWorld, money
from abm.observation import ObservationEngine
from abm.registry import ParameterRegistry, SimulationConfig

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class AbmBankGenerator:
    """Generate normal banking behavior, hard negatives, and AML scenarios."""

    def __init__(self, config: SimulationConfig, registry: ParameterRegistry) -> None:
        self.config = config
        self.registry = registry
        self.world = ReleaseWorld()
        self.release_time = config.simulation_end.astimezone(UTC) + timedelta(seconds=1)
        self.rng_population = _rng(config.simulation_seed, "population")
        self.rng_relationships = _rng(config.simulation_seed, "relationships")
        self.rng_behavior = _rng(config.simulation_seed, "normal-behavior")
        self.rng_observation = _rng(config.simulation_seed, "observation")
        self.rng_hard_negative = _rng(config.simulation_seed, "hard-negatives")
        self.rng_scenarios = _rng(config.simulation_seed, "aml-scenarios")
        self.observation = ObservationEngine(registry, self.rng_observation)

        self.counters: defaultdict[str, int] = defaultdict(int)
        self.customer_by_id: dict[str, dict[str, Any]] = {}
        self.business_by_id: dict[str, dict[str, Any]] = {}
        self.account_by_id: dict[str, dict[str, Any]] = {}
        self.merchant_by_id: dict[str, dict[str, Any]] = {}
        self.accounts_by_customer: defaultdict[str, list[str]] = defaultdict(list)
        self.primary_account_by_customer: dict[str, str] = {}
        self.customers_by_split: defaultdict[str, list[str]] = defaultdict(list)
        self.customers_by_segment_split: defaultdict[tuple[str, str], list[str]] = defaultdict(list)
        self.businesses_by_split: defaultdict[str, list[str]] = defaultdict(list)
        self.merchants_by_split: defaultdict[str, list[str]] = defaultdict(list)
        self.devices_by_customer: defaultdict[str, list[str]] = defaultdict(list)
        self.balance: dict[str, Decimal] = {}
        self.opening_balance: dict[str, Decimal] = {}
        self.scenario_entities: set[str] = set()
        self.hard_negative_entities: set[str] = set()
        self.split_windows = self._build_split_windows()

    def generate(self) -> ReleaseWorld:
        self._generate_population()
        self._generate_accounts()
        self._generate_devices()
        self._generate_merchants_and_relationships()
        self._generate_normal_behavior()

        from abm.scenarios.engine import ScenarioEngine
        from abm.scenarios.hard_negatives import HardNegativeEngine

        HardNegativeEngine(self, self.rng_hard_negative).generate()
        ScenarioEngine(self, self.rng_scenarios).generate()
        self._finalize_balances()
        self._finalize_split_assignments()
        return self.world

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def _generate_population(self) -> None:
        type_mix = self.registry.value("POP_CUSTOMER_TYPE_MIX_001")
        individual_mix = self.registry.value("POP_INDIVIDUAL_SEGMENT_MIX_001")
        business_mix = self.registry.value("POP_BUSINESS_SEGMENT_MIX_001")
        age_mix = self.registry.value("POP_AGE_BAND_MIX_001")
        region_mix = self.registry.value("POP_REGION_MIX_001")
        income_mix = self.registry.value("POP_INCOME_BAND_BY_SEGMENT_001")
        income_medians = self.registry.value("POP_INCOME_BAND_MEDIAN_VND_001")
        business_turnover = self.registry.value("POP_BUSINESS_MONTHLY_TURNOVER_MEDIAN_VND_001")
        split_weights = self.registry.value("SPLIT_POLICY_001")["entity_weights"]

        business_customer_specs: list[tuple[str, str]] = []
        for index in range(1, self.config.customer_count + 1):
            customer_id = f"CUS-{index:08d}"
            customer_kind = _weighted_choice(self.rng_population, type_mix)
            split = _weighted_choice(self.rng_population, split_weights)
            region = _weighted_choice(self.rng_population, region_mix)
            valid_from = self._historical_time(self.rng_population, 30, 2400)

            if customer_kind == "INDIVIDUAL":
                segment = _weighted_choice(self.rng_population, individual_mix)
                age_band = _weighted_choice(self.rng_population, age_mix)
                income_band = _weighted_choice(self.rng_population, income_mix[segment])
                monthly_scale = money(income_medians[income_band])
                customer_type = "INDIVIDUAL"
                business_id = None
                occupation = _occupation_code(segment, self.rng_population)
            else:
                segment = _weighted_choice(self.rng_population, business_mix)
                age_band = "NOT_APPLICABLE"
                income_band = _business_turnover_band(segment)
                monthly_scale = money(business_turnover[segment])
                customer_type = "CORPORATE" if segment == "CORPORATE" else "SME"
                business_id = self._next_id("BUS")
                occupation = None
                business_customer_specs.append((customer_id, business_id))

            row = {
                "schema_version": "2.0",
                "customer_id": customer_id,
                "source_system": "abm-bank",
                "source_record_id": customer_id,
                "customer_type": customer_type,
                "business_id": business_id,
                "status": "ACTIVE",
                "kyc_state": "VERIFIED",
                "risk_rating": _observable_risk_rating(segment, self.rng_population),
                "segment": segment,
                "age_band": age_band,
                "occupation_code": occupation,
                "declared_income_band": income_band,
                "monthly_scale_vnd": monthly_scale,
                "expected_monthly_turnover_vnd": _expected_turnover(monthly_scale, segment),
                "residency_country": "VN",
                "region_code": region,
                "customer_since": valid_from,
                "created_at": self.release_time,
                "valid_from": valid_from,
                "valid_to": None,
                "entity_split": split,
                "data_class": "C2_CONFIDENTIAL",
            }
            self.world.customers.append(row)
            self.customer_by_id[customer_id] = row
            self.customers_by_split[split].append(customer_id)
            self.customers_by_segment_split[(segment, split)].append(customer_id)

        industry_mix = self.registry.value("POP_BUSINESS_INDUSTRY_MIX_001")
        required_businesses = max(len(business_customer_specs), self.config.merchant_count)
        customer_for_business = {business_id: customer_id for customer_id, business_id in business_customer_specs}
        existing_business_ids = [business_id for _, business_id in business_customer_specs]
        all_business_ids = existing_business_ids + [
            self._next_id("BUS") for _ in range(required_businesses - len(existing_business_ids))
        ]

        for business_id in all_business_ids:
            customer_id = customer_for_business.get(business_id)
            if customer_id:
                customer = self.customer_by_id[customer_id]
                segment = customer["segment"]
                split = customer["entity_split"]
                valid_from = customer["valid_from"]
                turnover = customer["monthly_scale_vnd"]
            else:
                segment = _weighted_choice(self.rng_population, business_mix)
                split = _weighted_choice(self.rng_population, split_weights)
                valid_from = self._historical_time(self.rng_population, 60, 3600)
                turnover = money(business_turnover[segment])
            industry = _weighted_choice(self.rng_population, industry_mix)
            row = {
                "schema_version": "1.0",
                "business_id": business_id,
                "source_system": "abm-bank",
                "source_record_id": business_id,
                "customer_id": customer_id,
                "business_type": _business_type(segment),
                "industry_code": industry,
                "legal_form_code": _legal_form(segment),
                "employee_count_band": _employee_band(segment),
                "monthly_turnover_vnd": turnover,
                "annual_turnover_band": _business_turnover_band(segment),
                "registered_country": "VN",
                "registered_region_code": self.customer_by_id[customer_id]["region_code"]
                if customer_id
                else _weighted_choice(self.rng_population, region_mix),
                "established_at": valid_from,
                "status": "ACTIVE",
                "created_at": self.release_time,
                "valid_from": valid_from,
                "valid_to": None,
                "entity_split": split,
                "data_class": "C2_CONFIDENTIAL",
            }
            self.world.businesses.append(row)
            self.business_by_id[business_id] = row
            self.businesses_by_split[split].append(business_id)

    def _generate_accounts(self) -> None:
        count_mix = self.registry.value("POP_ACCOUNT_COUNT_001")
        product_order = self.registry.value("POP_ACCOUNT_PRODUCT_BY_INDEX_001")
        balance_months = self.registry.value("POP_OPENING_BALANCE_MONTHS_001")

        for customer in self.world.customers:
            count = int(_weighted_choice(self.rng_population, count_mix))
            for index in range(count):
                account_id = self._next_id("ACC")
                if index == 0:
                    product_type = product_order["PRIMARY"]
                    factor = Decimal(str(balance_months[customer["segment"]]))
                elif index == 1:
                    product_type = product_order["SECONDARY"]
                    factor = Decimal(str(balance_months[customer["segment"]])) * Decimal("0.45")
                else:
                    product_type = product_order["TERTIARY"]
                    factor = Decimal(str(balance_months[customer["segment"]])) * Decimal("0.30")
                opening = money(customer["monthly_scale_vnd"] * factor)
                opened_at = max(customer["valid_from"], self._historical_time(self.rng_population, 10, 1800))
                row = {
                    "schema_version": "2.0",
                    "account_id": account_id,
                    "source_system": "abm-bank",
                    "source_record_id": account_id,
                    "primary_customer_id": customer["customer_id"],
                    "owner_customer_ids": [customer["customer_id"]],
                    "product_type": product_type,
                    "currency": self.config.currency,
                    "status": "ACTIVE",
                    "opening_balance": opening,
                    "opened_at": opened_at,
                    "closed_at": None,
                    "branch_code": _branch_code(customer["region_code"]),
                    "opening_channel": "MOBILE" if customer["segment"] != "RETIRED" else "BRANCH",
                    "is_dormant_reactivated": False,
                    "created_at": self.release_time,
                    "valid_from": opened_at,
                    "valid_to": None,
                    "entity_split": customer["entity_split"],
                    "data_class": "C2_CONFIDENTIAL",
                }
                self.world.accounts.append(row)
                self.account_by_id[account_id] = row
                self.accounts_by_customer[customer["customer_id"]].append(account_id)
                if index == 0:
                    self.primary_account_by_customer[customer["customer_id"]] = account_id
                self.opening_balance[account_id] = opening
                self.balance[account_id] = opening
                self.add_relationship(
                    source_type="CUSTOMER",
                    source_id=customer["customer_id"],
                    target_type="ACCOUNT",
                    target_id=account_id,
                    relationship_type="OWNS_ACCOUNT" if index == 0 else "CO_OWNS_ACCOUNT",
                    direction="DIRECTED",
                    method="DETERMINISTIC",
                    confidence=1.0,
                    valid_from=opened_at,
                    dataset_split=customer["entity_split"],
                )

    def _generate_devices(self) -> None:
        adoption = self.registry.value("POP_DIGITAL_ADOPTION_001")
        device_count_mix = self.registry.value("POP_DEVICE_COUNT_001")
        normal_share = float(self.registry.value("OBS_NORMAL_DEVICE_SHARING_001"))

        for customer in self.world.customers:
            if self.rng_population.random() >= float(adoption[customer["segment"]]):
                continue
            count = int(_weighted_choice(self.rng_population, device_count_mix))
            for index in range(count):
                device_id = self._next_id("DEV")
                first_seen = max(
                    customer["valid_from"],
                    self.config.simulation_start.astimezone(UTC) - timedelta(days=self.rng_population.randint(1, 720)),
                )
                row = {
                    "schema_version": "1.0",
                    "device_id": device_id,
                    "source_system": "abm-bank-device-tokenizer",
                    "source_record_id": device_id,
                    "device_type": "MOBILE_APP" if index == 0 else "BROWSER",
                    "os_family": self.rng_population.choice(["ANDROID", "IOS", "WINDOWS", "MACOS", "LINUX"]),
                    "first_seen_at": first_seen,
                    "last_seen_at": self.config.simulation_end.astimezone(UTC),
                    "is_rooted_or_emulator": self.rng_population.random() < 0.012,
                    "created_at": self.release_time,
                    "valid_from": first_seen,
                    "valid_to": None,
                    "entity_split": customer["entity_split"],
                    "data_class": "C3_RESTRICTED",
                }
                self.world.devices.append(row)
                self.devices_by_customer[customer["customer_id"]].append(device_id)
                self.add_relationship(
                    source_type="CUSTOMER",
                    source_id=customer["customer_id"],
                    target_type="DEVICE",
                    target_id=device_id,
                    relationship_type="USES_DEVICE",
                    direction="DIRECTED",
                    method="DETERMINISTIC",
                    confidence=1.0,
                    valid_from=first_seen,
                    dataset_split=customer["entity_split"],
                )

        share_pairs = max(1, round(self.config.customer_count * normal_share / 2))
        for split, candidates in self.customers_by_split.items():
            eligible = [customer_id for customer_id in candidates if self.devices_by_customer[customer_id]]
            local_pairs = min(
                len(eligible) // 2, max(1, round(share_pairs * len(candidates) / self.config.customer_count))
            )
            self.rng_relationships.shuffle(eligible)
            for pair_index in range(local_pairs):
                first = eligible[pair_index * 2]
                second = eligible[pair_index * 2 + 1]
                shared_device = self.devices_by_customer[first][0]
                if shared_device not in self.devices_by_customer[second]:
                    self.devices_by_customer[second].append(shared_device)
                self.add_relationship(
                    source_type="CUSTOMER",
                    source_id=second,
                    target_type="DEVICE",
                    target_id=shared_device,
                    relationship_type="USES_DEVICE",
                    direction="DIRECTED",
                    method="DETERMINISTIC",
                    confidence=1.0,
                    valid_from=self.config.simulation_start.astimezone(UTC),
                    dataset_split=split,
                )
                self.add_relationship(
                    source_type="CUSTOMER",
                    source_id=first,
                    target_type="CUSTOMER",
                    target_id=second,
                    relationship_type="SHARED_DEVICE",
                    direction="UNDIRECTED",
                    method="PROBABILISTIC",
                    confidence=0.62,
                    valid_from=self.config.simulation_start.astimezone(UTC),
                    dataset_split=split,
                    inference_logic=f"Both customers used tokenized device {shared_device}; legitimate household/workplace sharing control.",
                    observation_count=2,
                )

    def _generate_merchants_and_relationships(self) -> None:
        mcc_mix = self.registry.value("POP_MERCHANT_MCC_MIX_001")
        businesses = list(self.world.businesses)
        self.rng_relationships.shuffle(businesses)
        for index in range(self.config.merchant_count):
            business = businesses[index % len(businesses)]
            merchant_id = self._next_id("MER")
            row = {
                "schema_version": "1.0",
                "merchant_id": merchant_id,
                "source_system": "abm-bank-acquiring",
                "source_record_id": merchant_id,
                "business_id": business["business_id"],
                "merchant_category_code": str(_weighted_choice(self.rng_relationships, mcc_mix)),
                "acquiring_bank_code": "ABMBANK",
                "country": "VN",
                "region_code": business["registered_region_code"],
                "status": "ACTIVE",
                "created_at": self.release_time,
                "valid_from": business["valid_from"],
                "valid_to": None,
                "entity_split": business["entity_split"],
                "data_class": "C1_INTERNAL",
            }
            self.world.merchants.append(row)
            self.merchant_by_id[merchant_id] = row
            self.merchants_by_split[business["entity_split"]].append(merchant_id)
            self.add_relationship(
                source_type="MERCHANT",
                source_id=merchant_id,
                target_type="LEGAL_ENTITY",
                target_id=business["business_id"],
                relationship_type="MERCHANT_OPERATED_BY",
                direction="DIRECTED",
                method="DETERMINISTIC",
                confidence=1.0,
                valid_from=business["valid_from"],
                dataset_split=business["entity_split"],
            )

        for customer in self.world.customers:
            if customer["business_id"]:
                candidates = [
                    item
                    for item in self.customers_by_split[customer["entity_split"]]
                    if self.customer_by_id[item]["customer_type"] == "INDIVIDUAL"
                ]
                if candidates:
                    owner = self.rng_relationships.choice(candidates)
                    self.add_relationship(
                        source_type="CUSTOMER",
                        source_id=owner,
                        target_type="LEGAL_ENTITY",
                        target_id=customer["business_id"],
                        relationship_type="BENEFICIAL_OWNER",
                        direction="DIRECTED",
                        method="DETERMINISTIC",
                        confidence=1.0,
                        valid_from=customer["valid_from"],
                        dataset_split=customer["entity_split"],
                    )
            elif customer["segment"] == "SALARIED":
                employers = self.businesses_by_split[customer["entity_split"]]
                if employers:
                    employer = self.rng_relationships.choice(employers)
                    self.add_relationship(
                        source_type="CUSTOMER",
                        source_id=customer["customer_id"],
                        target_type="LEGAL_ENTITY",
                        target_id=employer,
                        relationship_type="EMPLOYED_BY",
                        direction="DIRECTED",
                        method="DETERMINISTIC",
                        confidence=1.0,
                        valid_from=customer["valid_from"],
                        dataset_split=customer["entity_split"],
                    )

    # ------------------------------------------------------------------
    # Normal behavior
    # ------------------------------------------------------------------

    def _generate_normal_behavior(self) -> None:
        rates = self.registry.value("TXN_DAILY_RATE_BY_SEGMENT_001")
        mixes = self.registry.value("TXN_TYPE_MIX_BY_SEGMENT_001")
        weekend = self.registry.value("TXN_WEEKEND_FACTOR_001")
        salary_schedule = self.registry.value("TXN_SALARY_SCHEDULE_001")

        for customer in self.world.customers:
            customer_id = customer["customer_id"]
            primary_account = self.primary_account_by_customer[customer_id]
            split = customer["entity_split"]
            start_day, end_day = self.split_windows[split]
            is_business = customer["customer_type"] != "INDIVIDUAL"
            mix = mixes["BUSINESS" if is_business else "INDIVIDUAL"]
            base_rate = float(rates[customer["segment"]])

            if customer["segment"] == "SALARIED":
                self._generate_salary(customer, primary_account, start_day, end_day, salary_schedule)

            current_day = start_day
            while current_day <= end_day:
                factor = (
                    float(weekend["BUSINESS" if is_business else "INDIVIDUAL"]) if current_day.weekday() >= 5 else 1.0
                )
                event_count = _poisson(self.rng_behavior, base_rate * factor)
                for _ in range(event_count):
                    transaction_type = _weighted_choice(self.rng_behavior, mix)
                    self._emit_normal_transaction(customer, primary_account, transaction_type, current_day)
                current_day += timedelta(days=1)

    def _generate_salary(
        self,
        customer: dict[str, Any],
        account_id: str,
        start_day: date,
        end_day: date,
        schedule: dict[str, Any],
    ) -> None:
        current = date(start_day.year, start_day.month, 1)
        while current <= end_day:
            scheduled_day = self.rng_behavior.choice(schedule["days"])
            last_day = _month_end(current.year, current.month).day
            scheduled_day = min(scheduled_day, last_day)
            event_day = date(current.year, current.month, scheduled_day)
            event_day += timedelta(
                days=self.rng_behavior.randint(-int(schedule["jitter_days"]), int(schedule["jitter_days"]))
            )
            if start_day <= event_day <= end_day:
                event_time = self._event_time(
                    event_day,
                    self.rng_behavior.randint(int(schedule["hour_start"]), int(schedule["hour_end"])),
                    self.rng_behavior,
                )
                salary_amount = money(
                    customer["monthly_scale_vnd"] * Decimal(str(self.rng_behavior.uniform(0.92, 1.08)))
                )
                self.add_transaction(
                    event_time=event_time,
                    source_counterparty_ref=self.external_ref(customer["customer_id"], "EMPLOYER"),
                    destination_account_id=account_id,
                    amount=salary_amount,
                    transaction_type="SALARY",
                    channel="BATCH",
                    customer_id=customer["customer_id"],
                    dataset_split=customer["entity_split"],
                    purpose_code="PAYROLL",
                    purpose_text="Monthly payroll",
                )
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

    def _emit_normal_transaction(
        self,
        customer: dict[str, Any],
        primary_account: str,
        transaction_type: str,
        event_day: date,
    ) -> None:
        is_business = customer["customer_type"] != "INDIVIDUAL"
        channel = self.choose_channel(transaction_type)
        hour_profile = "BUSINESS" if is_business else "RETAIL"
        hour = int(_weighted_choice(self.rng_behavior, self.registry.value("TXN_HOUR_WEIGHTS_001")[hour_profile]))
        event_time = self._event_time(event_day, hour, self.rng_behavior)
        amount = self.normal_amount(transaction_type, customer["segment"], self.rng_behavior)
        split = customer["entity_split"]
        customer_id = customer["customer_id"]
        purpose_code = transaction_type
        purpose_text = _purpose_text(transaction_type)
        merchant_id: str | None = None

        source_account_id: str | None = primary_account
        source_counterparty_ref: str | None = None
        destination_account_id: str | None = None
        destination_counterparty_ref: str | None = None

        if transaction_type == "TRANSFER":
            if self.rng_behavior.random() < 0.38:
                source_account_id = None
                source_counterparty_ref = self.external_ref(customer_id, "FAMILY", self.rng_behavior.randrange(4))
                destination_account_id = primary_account
            elif self.rng_behavior.random() < 0.30:
                candidates = self.primary_accounts_in_split(split, exclude=primary_account)
                if candidates:
                    destination_account_id = self.rng_behavior.choice(candidates)
                else:
                    destination_counterparty_ref = self.external_ref(
                        customer_id, "BENEFICIARY", self.rng_behavior.randrange(8)
                    )
            else:
                destination_counterparty_ref = self.external_ref(
                    customer_id, "BENEFICIARY", self.rng_behavior.randrange(8)
                )
        elif transaction_type == "BILL_PAYMENT":
            destination_counterparty_ref = self.external_ref(customer_id, "BILLER", self.rng_behavior.randrange(5))
        elif transaction_type == "MERCHANT_PURCHASE":
            merchants = self.merchants_by_split[split] or list(self.merchant_by_id)
            merchant_id = self.rng_behavior.choice(merchants)
            destination_counterparty_ref = f"CPY-{merchant_id}"
        elif transaction_type == "CASH_DEPOSIT":
            source_account_id = None
            source_counterparty_ref = self.external_ref(customer_id, "CASH_SOURCE")
            destination_account_id = primary_account
        elif transaction_type == "CASH_WITHDRAWAL":
            destination_counterparty_ref = self.external_ref(customer_id, "CASH_WITHDRAWAL")
        elif transaction_type in {"BUSINESS_PAYMENT", "SUPPLIER_PAYMENT"}:
            if self.rng_behavior.random() < 0.20:
                candidates = self.primary_accounts_in_split(split, exclude=primary_account, business_only=True)
                if candidates:
                    destination_account_id = self.rng_behavior.choice(candidates)
                else:
                    destination_counterparty_ref = self.external_ref(
                        customer_id, "SUPPLIER", self.rng_behavior.randrange(12)
                    )
            else:
                destination_counterparty_ref = self.external_ref(
                    customer_id, "SUPPLIER", self.rng_behavior.randrange(12)
                )
        elif transaction_type == "LOAN_REPAYMENT":
            destination_counterparty_ref = self.external_ref(customer_id, "LOAN")
        elif transaction_type == "SAVINGS_TRANSFER":
            accounts = self.accounts_by_customer[customer_id]
            if len(accounts) > 1:
                destination_account_id = self.rng_behavior.choice(accounts[1:])
            else:
                destination_counterparty_ref = self.external_ref(customer_id, "SAVINGS")
        elif transaction_type == "INTERNATIONAL_PAYMENT":
            destination_counterparty_ref = self.external_ref(
                customer_id, "INTERNATIONAL", self.rng_behavior.randrange(6)
            )
        else:
            destination_counterparty_ref = self.external_ref(customer_id, "OTHER")

        if source_account_id:
            available = self.balance[source_account_id]
            cap = money(max(Decimal("10000"), available * Decimal("0.35")))
            amount = min(amount, cap)
            if amount > available or amount < Decimal("10000"):
                return

        self.add_transaction(
            event_time=event_time,
            source_account_id=source_account_id,
            source_counterparty_ref=source_counterparty_ref,
            destination_account_id=destination_account_id,
            destination_counterparty_ref=destination_counterparty_ref,
            amount=amount,
            transaction_type=transaction_type,
            channel=channel,
            customer_id=customer_id,
            dataset_split=split,
            merchant_id=merchant_id,
            purpose_code=purpose_code,
            purpose_text=purpose_text,
        )

    # ------------------------------------------------------------------
    # Shared helpers for hard-negative and AML scenario engines
    # ------------------------------------------------------------------

    def add_transaction(
        self,
        *,
        event_time: datetime,
        amount: Decimal | int | float | str,
        transaction_type: str,
        channel: str,
        customer_id: str,
        dataset_split: str,
        source_account_id: str | None = None,
        source_counterparty_ref: str | None = None,
        destination_account_id: str | None = None,
        destination_counterparty_ref: str | None = None,
        merchant_id: str | None = None,
        purpose_code: str | None = None,
        purpose_text: str | None = None,
        quality_flags: list[str] | None = None,
    ) -> str | None:
        amount_value = money(amount)
        if amount_value <= 0:
            return None
        if bool(source_account_id) == bool(source_counterparty_ref):
            raise ValueError("transaction requires exactly one source endpoint")
        if bool(destination_account_id) == bool(destination_counterparty_ref):
            raise ValueError("transaction requires exactly one destination endpoint")
        if source_account_id and source_account_id == destination_account_id:
            raise ValueError("self-loop transaction is not allowed")
        if source_account_id and self.balance[source_account_id] < amount_value:
            return None

        if source_account_id:
            self.balance[source_account_id] = money(self.balance[source_account_id] - amount_value)
        if destination_account_id:
            self.balance[destination_account_id] = money(self.balance[destination_account_id] + amount_value)

        transaction_id = self._next_id("TXN")
        event_id = self._next_id("EVT")
        posting_time = event_time + timedelta(seconds=self.rng_behavior.randint(1, 45))
        device_id: str | None = None
        session_id: str | None = None
        if channel in self.registry.value("TXN_SESSION_CHANNELS_001") and self.devices_by_customer[customer_id]:
            device_id = self.rng_behavior.choice(self.devices_by_customer[customer_id])
            session_id = self._add_session(customer_id, device_id, event_time, channel, dataset_split)

        raw = {
            "schema_version": "1.0",
            "transaction_id": transaction_id,
            "event_id": event_id,
            "source_system": "abm-bank",
            "source_record_id": transaction_id,
            "event_time": event_time.astimezone(UTC),
            "posting_time": posting_time.astimezone(UTC),
            "available_from": posting_time.astimezone(UTC),
            "source_account_id": source_account_id,
            "source_counterparty_ref": source_counterparty_ref,
            "destination_account_id": destination_account_id,
            "destination_counterparty_ref": destination_counterparty_ref,
            "amount": amount_value,
            "currency": self.config.currency,
            "transaction_type": transaction_type,
            "channel": channel,
            "merchant_id": merchant_id,
            "device_id": device_id,
            "session_id": session_id,
            "purpose_code": purpose_code,
            "purpose_text": purpose_text,
            "status": "POSTED",
            "created_at": self.release_time,
            "quality_flags": list(quality_flags or []),
            "dataset_split": dataset_split,
            "data_class": "C2_CONFIDENTIAL",
        }
        projected = self.observation.project_transaction(raw)
        self.world.transactions.append(projected)
        return transaction_id

    def _add_session(
        self,
        customer_id: str,
        device_id: str,
        event_time: datetime,
        channel: str,
        dataset_split: str,
    ) -> str:
        session_id = self._next_id("SES")
        ip_bucket = self.rng_behavior.randrange(max(50, self.config.customer_count // 8))
        nat = self.rng_behavior.random() < 0.22
        row = {
            "schema_version": "1.0",
            "session_id": session_id,
            "customer_id": customer_id,
            "device_id": device_id,
            "event_type": "LOGIN_SUCCESS",
            "event_time": (event_time - timedelta(minutes=self.rng_behavior.randint(1, 15))).astimezone(UTC),
            "available_from": event_time.astimezone(UTC),
            "channel": channel,
            "ip_token": f"IPT-{ip_bucket:08d}",
            "country": "VN",
            "region_code": self.customer_by_id[customer_id]["region_code"],
            "is_vpn_or_proxy": self.rng_behavior.random() < 0.025,
            "is_shared_nat_suspected": nat,
            "authentication_method": self.rng_behavior.choice(["OTP_APP", "BIOMETRIC", "PASSWORD"]),
            "authentication_successful": True,
            "created_at": self.release_time,
            "dataset_split": dataset_split,
            "data_class": "C3_RESTRICTED",
        }
        self.world.sessions.append(row)
        return session_id

    def add_relationship(
        self,
        *,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        relationship_type: str,
        direction: str,
        method: str,
        confidence: float,
        valid_from: datetime,
        dataset_split: str,
        inference_logic: str | None = None,
        observation_count: int = 1,
    ) -> str:
        relationship_id = self._next_id("REL")
        row = {
            "schema_version": "2.0",
            "relationship_id": relationship_id,
            "source_entity_type": source_type,
            "source_entity_id": source_id,
            "target_entity_type": target_type,
            "target_entity_id": target_id,
            "relationship_type": relationship_type,
            "direction": direction,
            "method": method,
            "confidence": float(confidence),
            "is_fact": method in {"DETERMINISTIC", "ANALYST_CONFIRMED"},
            "inference_logic": inference_logic,
            "observation_count": int(observation_count),
            "created_at": self.release_time,
            "valid_from": valid_from.astimezone(UTC),
            "valid_to": None,
            "known_from": valid_from.astimezone(UTC),
            "source_system": "abm-bank-observation",
            "dataset_split": dataset_split,
            "data_class": "C2_CONFIDENTIAL",
        }
        self.world.relationships.append(row)
        return relationship_id

    def choose_customer(
        self,
        rng: random.Random,
        split: str,
        segments: Iterable[str] | None = None,
        exclude: set[str] | None = None,
    ) -> str:
        excluded = exclude or set()
        if segments:
            candidates = [
                customer_id
                for segment in segments
                for customer_id in self.customers_by_segment_split[(segment, split)]
                if customer_id not in excluded
            ]
        else:
            candidates = [customer_id for customer_id in self.customers_by_split[split] if customer_id not in excluded]
        if not candidates:
            raise ValueError(f"no eligible customers for split={split}, segments={segments}")
        return rng.choice(candidates)

    def primary_accounts_in_split(
        self,
        split: str,
        *,
        exclude: str | None = None,
        business_only: bool = False,
    ) -> list[str]:
        result: list[str] = []
        for customer_id in self.customers_by_split[split]:
            customer = self.customer_by_id[customer_id]
            if business_only and customer["customer_type"] == "INDIVIDUAL":
                continue
            account_id = self.primary_account_by_customer[customer_id]
            if account_id != exclude:
                result.append(account_id)
        return result

    def account_customer(self, account_id: str) -> str:
        return str(self.account_by_id[account_id]["primary_customer_id"])

    def external_ref(self, customer_id: str, category: str, index: int = 0) -> str:
        digest = hashlib.sha256(f"{self.config.dataset_version}|{customer_id}|{category}|{index}".encode()).hexdigest()[
            :16
        ]
        return f"CPY-{category}-{digest}".upper()

    def choose_channel(self, transaction_type: str) -> str:
        table = self.registry.value("TXN_CHANNEL_BY_TYPE_001")
        return str(_weighted_choice(self.rng_behavior, table[transaction_type]))

    def normal_amount(self, transaction_type: str, segment: str, rng: random.Random) -> Decimal:
        medians = self.registry.value("TXN_AMOUNT_MEDIAN_VND_001")
        scales = self.registry.value("TXN_SEGMENT_AMOUNT_SCALE_001")
        sigmas = self.registry.value("TXN_AMOUNT_LOG_SIGMA_001")
        median = float(medians[transaction_type]) * float(scales[segment])
        sigma = float(sigmas.get(transaction_type, sigmas["DEFAULT"]))
        sampled = rng.lognormvariate(math.log(max(1.0, median)), sigma)
        return money(max(1000, sampled))

    def event_time_in_split(self, split: str, rng: random.Random) -> datetime:
        start_day, end_day = self.split_windows[split]
        days = (end_day - start_day).days
        event_day = start_day + timedelta(days=rng.randint(0, max(0, days)))
        return self._event_time(event_day, rng.randint(7, 21), rng)

    def record_entity_label(
        self,
        *,
        entity_id: str,
        entity_type: str,
        scenario_instance_id: str,
        network_id: str,
        role: str,
        active_from: datetime,
        active_to: datetime,
        dataset_split: str,
    ) -> None:
        release_end = self.config.simulation_end.astimezone(UTC)
        active_to = min(active_to.astimezone(UTC), release_end)
        active_from = min(active_from.astimezone(UTC), active_to)
        self.world.entity_labels.append(
            {
                "entity_id": entity_id,
                "entity_type": entity_type,
                "scenario_instance_id": scenario_instance_id,
                "network_id": network_id,
                "role": role,
                "label_type": "AML_INVOLVEMENT",
                "label_value": "INVOLVED",
                "active_from": active_from,
                "active_to": active_to,
                "label_source": "SIMULATOR_GROUND_TRUTH",
                "dataset_split": dataset_split,
            }
        )
        self.world.network_members.append(
            {
                "network_id": network_id,
                "entity_id": entity_id,
                "entity_type": entity_type,
                "role": role,
                "active_from": active_from,
                "active_to": active_to,
                "dataset_split": dataset_split,
            }
        )

    def record_transaction_label(
        self,
        transaction_id: str | None,
        scenario_instance_id: str,
        network_id: str,
        stage: str,
        dataset_split: str,
    ) -> None:
        if transaction_id is None:
            raise ValueError("scenario transaction could not be emitted because of insufficient balance")
        self.world.transaction_labels.append(
            {
                "transaction_id": transaction_id,
                "scenario_instance_id": scenario_instance_id,
                "network_id": network_id,
                "label_type": "AML_INVOLVEMENT",
                "label_value": "SYNTHETIC_TYPOLOGY_STEP",
                "scenario_stage": stage,
                "label_source": "SIMULATOR_GROUND_TRUTH",
                "dataset_split": dataset_split,
            }
        )

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    def _finalize_balances(self) -> None:
        for account in self.world.accounts:
            account_id = account["account_id"]
            self.world.balance_snapshots.extend(
                [
                    {
                        "account_id": account_id,
                        "snapshot_time": self.config.simulation_start.astimezone(UTC),
                        "balance": self.opening_balance[account_id],
                        "currency": self.config.currency,
                        "snapshot_type": "OPENING",
                        "dataset_split": account["entity_split"],
                    },
                    {
                        "account_id": account_id,
                        "snapshot_time": self.config.simulation_end.astimezone(UTC),
                        "balance": self.balance[account_id],
                        "currency": self.config.currency,
                        "snapshot_type": "CLOSING",
                        "dataset_split": account["entity_split"],
                    },
                ]
            )

    def _finalize_split_assignments(self) -> None:
        for customer in self.world.customers:
            self.world.split_assignments.append(
                {
                    "entity_id": customer["customer_id"],
                    "entity_type": "CUSTOMER",
                    "dataset_split": customer["entity_split"],
                    "assignment_reason": "ENTITY_COHORT_AND_CHRONOLOGICAL_WINDOW",
                }
            )
        for account in self.world.accounts:
            self.world.split_assignments.append(
                {
                    "entity_id": account["account_id"],
                    "entity_type": "ACCOUNT",
                    "dataset_split": account["entity_split"],
                    "assignment_reason": "INHERITED_FROM_OWNER_CUSTOMER",
                }
            )
        for scenario in self.world.scenario_instances:
            self.world.split_assignments.append(
                {
                    "entity_id": scenario["scenario_instance_id"],
                    "entity_type": "SCENARIO_INSTANCE",
                    "dataset_split": scenario["dataset_split"],
                    "assignment_reason": "NETWORK_ISOLATED_BENCHMARK_QUOTA",
                }
            )

    def _build_split_windows(self) -> dict[str, tuple[date, date]]:
        policy = self.registry.value("SPLIT_POLICY_001")["day_fractions"]
        first = self.config.simulation_start.date()
        total = self.config.duration_days
        result: dict[str, tuple[date, date]] = {}
        for split, fractions in policy.items():
            start_index = min(total - 1, math.floor(float(fractions[0]) * total))
            end_index = min(total - 1, max(start_index, math.ceil(float(fractions[1]) * total) - 1))
            result[split] = (first + timedelta(days=start_index), first + timedelta(days=end_index))
        return result

    def _next_id(self, prefix: str) -> str:
        self.counters[prefix] += 1
        return f"{prefix}-{self.counters[prefix]:010d}"

    def _historical_time(self, rng: random.Random, minimum_days: int, maximum_days: int) -> datetime:
        return (self.config.simulation_start - timedelta(days=rng.randint(minimum_days, maximum_days))).astimezone(UTC)

    @staticmethod
    def _event_time(event_day: date, hour: int, rng: random.Random) -> datetime:
        local = datetime.combine(
            event_day, time(hour=hour, minute=rng.randrange(60), second=rng.randrange(60)), tzinfo=VN_TZ
        )
        return local.astimezone(UTC)


def _rng(seed: int, namespace: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{namespace}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _weighted_choice(rng: random.Random, weights: dict[Any, Any]) -> Any:
    items = list(weights.items())
    total = sum(float(weight) for _, weight in items)
    if total <= 0:
        raise ValueError("weighted choice requires positive total weight")
    marker = rng.random() * total
    cumulative = 0.0
    for item, weight in items:
        cumulative += float(weight)
        if marker <= cumulative:
            return item
    return items[-1][0]


def _poisson(rng: random.Random, rate: float) -> int:
    if rate <= 0:
        return 0
    if rate > 12:
        return max(0, round(rng.gauss(rate, math.sqrt(rate))))
    threshold = math.exp(-rate)
    product = 1.0
    count = 0
    while product > threshold:
        count += 1
        product *= rng.random()
    return count - 1


def _occupation_code(segment: str, rng: random.Random) -> str:
    choices = {
        "SALARIED": ["OFFICE", "ENGINEERING", "EDUCATION", "HEALTH", "INDUSTRIAL"],
        "HOUSEHOLD": ["SELF_EMPLOYED", "RETAIL_TRADER", "SERVICE_WORKER", "CRAFT"],
        "AFFLUENT": ["EXECUTIVE", "PROFESSIONAL", "INVESTOR"],
        "STUDENT": ["STUDENT"],
        "RETIRED": ["RETIRED"],
    }
    return rng.choice(choices[segment])


def _observable_risk_rating(segment: str, rng: random.Random) -> str:
    high_probability = 0.05 if segment in {"CORPORATE", "AFFLUENT"} else 0.015
    marker = rng.random()
    if marker < high_probability:
        return "HIGH"
    if marker < 0.26:
        return "MEDIUM"
    return "LOW"


def _expected_turnover(monthly_scale: Decimal, segment: str) -> Decimal:
    if segment in {"HOUSEHOLD_BUSINESS", "SME", "CORPORATE"}:
        return money(monthly_scale)
    return money(monthly_scale * Decimal("1.25"))


def _business_type(segment: str) -> str:
    return {
        "HOUSEHOLD_BUSINESS": "HOUSEHOLD_BUSINESS",
        "SME": "LIMITED_LIABILITY",
        "CORPORATE": "JOINT_STOCK",
    }[segment]


def _legal_form(segment: str) -> str:
    return {"HOUSEHOLD_BUSINESS": "HHB", "SME": "LLC", "CORPORATE": "JSC"}[segment]


def _employee_band(segment: str) -> str:
    return {"HOUSEHOLD_BUSINESS": "1_9", "SME": "10_199", "CORPORATE": "200_PLUS"}[segment]


def _business_turnover_band(segment: str) -> str:
    return {"HOUSEHOLD_BUSINESS": "LT_3B", "SME": "3B_50B", "CORPORATE": "GE_50B"}[segment]


def _branch_code(region: str) -> str:
    return {"HCM": "BR-HCM", "HN": "BR-HN", "OTHER_URBAN": "BR-URB", "RURAL": "BR-RUR"}[region]


def _purpose_text(transaction_type: str) -> str:
    return {
        "TRANSFER": "Personal transfer",
        "BILL_PAYMENT": "Utility or recurring bill",
        "MERCHANT_PURCHASE": "Merchant purchase",
        "CASH_DEPOSIT": "Cash deposit",
        "CASH_WITHDRAWAL": "Cash withdrawal",
        "BUSINESS_PAYMENT": "Business operating payment",
        "SUPPLIER_PAYMENT": "Supplier invoice payment",
        "LOAN_REPAYMENT": "Scheduled loan repayment",
        "SAVINGS_TRANSFER": "Transfer to savings",
        "INTERNATIONAL_PAYMENT": "International goods or services payment",
    }.get(transaction_type, "Other payment")


def _month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)
