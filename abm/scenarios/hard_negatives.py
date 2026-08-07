"""Legitimate behavior deliberately shaped to collide with AML indicators."""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal
from typing import Any

from abm.models import money


class HardNegativeEngine:
    def __init__(self, host: Any, rng: random.Random) -> None:
        self.host = host
        self.rng = rng
        self.quotas = host.registry.value("HARD_NEGATIVE_QUOTAS_001")
        self.pattern = host.registry.value("HARD_NEGATIVE_PATTERN_001")

    def generate(self) -> None:
        handlers = {
            "SALARY_DISBURSEMENT": self._salary_disbursement,
            "MARKETPLACE_SELLER": self._marketplace_seller,
            "FAMILY_REMITTANCE_HUB": self._family_remittance,
            "SEASONAL_BUSINESS": self._seasonal_business,
            "PROPERTY_OR_INSURANCE_EVENT": self._property_or_insurance,
            "TREASURY_MOVEMENT": self._treasury_movement,
        }
        for scenario_type, configured_count in self.quotas.items():
            count = max(1, round(int(configured_count) * self.host.config.hard_negative_scale))
            for split in _split_allocation(count):
                handlers[scenario_type](split)

    def _salary_disbursement(self, split: str) -> None:
        employer = self._customer(split, ["SME", "CORPORATE"])
        employer_account = self.host.primary_account_by_customer[employer]
        employees = self._customers(split, ["SALARIED"], self.rng.randint(8, 24), exclude={employer})
        base = self._base_time(split, 1)
        total = money(sum((self.host.customer_by_id[item]["monthly_scale_vnd"] for item in employees), Decimal("0")))
        funding = self.host.add_transaction(
            event_time=base - timedelta(hours=6),
            source_counterparty_ref=self.host.external_ref(employer, "BUSINESS_REVENUE"),
            destination_account_id=employer_account,
            amount=money(total * Decimal("1.05")),
            transaction_type="BUSINESS_PAYMENT",
            channel="BATCH",
            customer_id=employer,
            dataset_split=split,
            purpose_code="PAYROLL_FUNDING",
            purpose_text="Payroll funding",
        )
        transaction_ids = [funding] if funding else []
        for index, employee in enumerate(employees):
            amount = self.host.customer_by_id[employee]["monthly_scale_vnd"]
            transaction_id = self.host.add_transaction(
                event_time=base + timedelta(minutes=index * 2),
                source_account_id=employer_account,
                destination_account_id=self.host.primary_account_by_customer[employee],
                amount=amount,
                transaction_type="SALARY",
                channel="BATCH",
                customer_id=employer,
                dataset_split=split,
                purpose_code="PAYROLL",
                purpose_text="Employee payroll disbursement",
            )
            if transaction_id:
                transaction_ids.append(transaction_id)
        self._record(
            "SALARY_DISBURSEMENT",
            split,
            [employer, *employees],
            transaction_ids,
            base - timedelta(hours=6),
            base + timedelta(hours=2),
            "Registered employer pays a recurring employee cohort.",
            "One account receives operating funds and rapidly fans out similar payments.",
            "Fan-out, rapid movement, many beneficiaries, low end balance.",
        )

    def _marketplace_seller(self, split: str) -> None:
        seller = self._customer(split, ["HOUSEHOLD_BUSINESS", "SME"])
        account = self.host.primary_account_by_customer[seller]
        base = self._base_time(split, 2)
        count = self.rng.randint(int(self.pattern["counterparties"][0]), int(self.pattern["counterparties"][1]))
        transaction_ids: list[str] = []
        gross = Decimal("0")
        for index in range(count):
            amount = money(self.rng.uniform(120000, 2800000))
            gross += amount
            transaction_id = self.host.add_transaction(
                event_time=base + timedelta(minutes=self.rng.randint(0, 1200)),
                source_counterparty_ref=self.host.external_ref(seller, "BUYER", index),
                destination_account_id=account,
                amount=amount,
                transaction_type="MERCHANT_PURCHASE",
                channel=self.rng.choice(["MOBILE", "CARD", "POS"]),
                customer_id=seller,
                dataset_split=split,
                purpose_code="MARKETPLACE_SALE",
                purpose_text="Online marketplace order settlement",
            )
            if transaction_id:
                transaction_ids.append(transaction_id)
        payout = self.host.add_transaction(
            event_time=base + timedelta(days=1, hours=2),
            source_account_id=account,
            destination_counterparty_ref=self.host.external_ref(seller, "SUPPLIER"),
            amount=money(gross * Decimal("0.68")),
            transaction_type="SUPPLIER_PAYMENT",
            channel="INTERNET",
            customer_id=seller,
            dataset_split=split,
            purpose_code="INVENTORY",
            purpose_text="Inventory replenishment",
        )
        if payout:
            transaction_ids.append(payout)
        self._record(
            "MARKETPLACE_SELLER",
            split,
            [seller],
            transaction_ids,
            base,
            base + timedelta(days=2),
            "Popular online seller receives many small customer payments and pays suppliers.",
            "High fan-in followed by a large supplier debit.",
            "Collection-account and rapid-turnover rules.",
        )

    def _family_remittance(self, split: str) -> None:
        hub = self._customer(split, ["SALARIED", "HOUSEHOLD", "RETIRED"])
        account = self.host.primary_account_by_customer[hub]
        base = self._base_time(split, 3)
        incoming_count = self.rng.randint(8, 18)
        transaction_ids: list[str] = []
        total = Decimal("0")
        for index in range(incoming_count):
            amount = money(self.rng.uniform(500000, 6500000))
            total += amount
            transaction_id = self.host.add_transaction(
                event_time=base + timedelta(hours=self.rng.randint(0, 36)),
                source_counterparty_ref=self.host.external_ref(hub, "FAMILY_MEMBER", index),
                destination_account_id=account,
                amount=amount,
                transaction_type="TRANSFER",
                channel="MOBILE",
                customer_id=hub,
                dataset_split=split,
                purpose_code="FAMILY_SUPPORT",
                purpose_text="Family support contribution",
            )
            if transaction_id:
                transaction_ids.append(transaction_id)
        for index in range(self.rng.randint(3, 7)):
            amount = money(total / Decimal(str(self.rng.randint(6, 10))))
            transaction_id = self.host.add_transaction(
                event_time=base + timedelta(days=2, hours=index),
                source_account_id=account,
                destination_counterparty_ref=self.host.external_ref(hub, "DEPENDENT", index),
                amount=amount,
                transaction_type="TRANSFER",
                channel="MOBILE",
                customer_id=hub,
                dataset_split=split,
                purpose_code="FAMILY_SUPPORT",
                purpose_text="Family living support",
            )
            if transaction_id:
                transaction_ids.append(transaction_id)
        self._record(
            "FAMILY_REMITTANCE_HUB",
            split,
            [hub],
            transaction_ids,
            base,
            base + timedelta(days=3),
            "Family coordinator pools contributions and redistributes support to dependents.",
            "Many unrelated-looking senders and several outgoing beneficiaries.",
            "Funnel, fan-in/fan-out, and new-beneficiary rules.",
        )

    def _seasonal_business(self, split: str) -> None:
        business = self._customer(split, ["HOUSEHOLD_BUSINESS", "SME", "CORPORATE"])
        account = self.host.primary_account_by_customer[business]
        base = self._base_time(split, 4)
        count = self.rng.randint(int(self.pattern["burst_transactions"][0]), int(self.pattern["burst_transactions"][1]))
        transaction_ids: list[str] = []
        total = Decimal("0")
        for index in range(count):
            amount = money(self.rng.uniform(1000000, 18000000))
            total += amount
            transaction_id = self.host.add_transaction(
                event_time=base + timedelta(minutes=self.rng.randint(0, 1440)),
                source_counterparty_ref=self.host.external_ref(business, "SEASONAL_CUSTOMER", index),
                destination_account_id=account,
                amount=amount,
                transaction_type="BUSINESS_PAYMENT",
                channel=self.rng.choice(["API", "INTERNET", "BRANCH"]),
                customer_id=business,
                dataset_split=split,
                purpose_code="SEASONAL_SALES",
                purpose_text="Seasonal campaign sales",
            )
            if transaction_id:
                transaction_ids.append(transaction_id)
        outgoing = self.host.add_transaction(
            event_time=base + timedelta(days=2),
            source_account_id=account,
            destination_counterparty_ref=self.host.external_ref(business, "SEASONAL_SUPPLIER"),
            amount=money(total * Decimal("0.58")),
            transaction_type="SUPPLIER_PAYMENT",
            channel="BATCH",
            customer_id=business,
            dataset_split=split,
            purpose_code="SEASONAL_INVENTORY",
            purpose_text="Seasonal inventory settlement",
        )
        if outgoing:
            transaction_ids.append(outgoing)
        self._record(
            "SEASONAL_BUSINESS",
            split,
            [business],
            transaction_ids,
            base,
            base + timedelta(days=3),
            "Seasonal sales campaign creates a short legitimate revenue burst.",
            "Sudden fan-in and turnover far above the customer's prior baseline.",
            "Peer-deviation, burst, and flow-through rules.",
        )

    def _property_or_insurance(self, split: str) -> None:
        customer = self._customer(split, ["SALARIED", "HOUSEHOLD", "AFFLUENT", "RETIRED"])
        account = self.host.primary_account_by_customer[customer]
        base = self._base_time(split, 2)
        lower, upper = self.pattern["large_event_amount_vnd"]
        amount = money(self.rng.uniform(float(lower), float(upper)))
        source_kind = self.rng.choice(["PROPERTY_BUYER", "INSURER"])
        transaction_ids: list[str] = []
        credit = self.host.add_transaction(
            event_time=base,
            source_counterparty_ref=self.host.external_ref(customer, source_kind),
            destination_account_id=account,
            amount=amount,
            transaction_type="TRANSFER",
            channel="BRANCH",
            customer_id=customer,
            dataset_split=split,
            purpose_code="ASSET_EVENT",
            purpose_text="Documented property sale or insurance payout",
        )
        if credit:
            transaction_ids.append(credit)
        for index, fraction in enumerate([Decimal("0.18"), Decimal("0.12"), Decimal("0.08")]):
            debit = self.host.add_transaction(
                event_time=base + timedelta(hours=10 + index * 8),
                source_account_id=account,
                destination_counterparty_ref=self.host.external_ref(customer, "ASSET_USE", index),
                amount=money(amount * fraction),
                transaction_type="TRANSFER",
                channel="INTERNET",
                customer_id=customer,
                dataset_split=split,
                purpose_code="ASSET_ALLOCATION",
                purpose_text="Documented asset proceeds allocation",
            )
            if debit:
                transaction_ids.append(debit)
        self._record(
            "PROPERTY_OR_INSURANCE_EVENT",
            split,
            [customer],
            transaction_ids,
            base,
            base + timedelta(days=2),
            "Documented property sale or insurance claim produces a one-off large credit.",
            "Large profile deviation followed by several new-beneficiary payments.",
            "Large-value, velocity, and profile-mismatch rules.",
        )

    def _treasury_movement(self, split: str) -> None:
        first = self._customer(split, ["SME", "CORPORATE"])
        second = self._customer(split, ["SME", "CORPORATE"], exclude={first})
        first_account = self.host.primary_account_by_customer[first]
        second_account = self.host.primary_account_by_customer[second]
        base = self._base_time(split, 2)
        amount = money(self.rng.uniform(250000000, 1800000000))
        transaction_ids: list[str] = []
        funding = self.host.add_transaction(
            event_time=base - timedelta(hours=3),
            source_counterparty_ref=self.host.external_ref(first, "TREASURY_SOURCE"),
            destination_account_id=first_account,
            amount=amount,
            transaction_type="BUSINESS_PAYMENT",
            channel="BATCH",
            customer_id=first,
            dataset_split=split,
            purpose_code="TREASURY_FUNDING",
            purpose_text="Group treasury funding",
        )
        if funding:
            transaction_ids.append(funding)
        moved = self.host.add_transaction(
            event_time=base,
            source_account_id=first_account,
            destination_account_id=second_account,
            amount=money(amount * Decimal("0.97")),
            transaction_type="BUSINESS_PAYMENT",
            channel="API",
            customer_id=first,
            dataset_split=split,
            purpose_code="INTERCOMPANY_TREASURY",
            purpose_text="Documented intercompany treasury sweep",
        )
        if moved:
            transaction_ids.append(moved)
        returned = self.host.add_transaction(
            event_time=base + timedelta(hours=18),
            source_account_id=second_account,
            destination_account_id=first_account,
            amount=money(amount * Decimal("0.955")),
            transaction_type="BUSINESS_PAYMENT",
            channel="API",
            customer_id=second,
            dataset_split=split,
            purpose_code="INTERCOMPANY_TREASURY",
            purpose_text="Documented treasury sweep return",
        )
        if returned:
            transaction_ids.append(returned)
        self._record(
            "TREASURY_MOVEMENT",
            split,
            [first, second],
            transaction_ids,
            base - timedelta(hours=3),
            base + timedelta(days=1),
            "Related businesses perform documented liquidity sweeps.",
            "Rapid high-value back-and-forth movement with low retained balance.",
            "Circular flow, rapid pass-through, and layering rules.",
        )

    def _record(
        self,
        scenario_type: str,
        split: str,
        entity_ids: list[str],
        transaction_ids: list[str],
        active_from: Any,
        active_to: Any,
        legitimate_reason: str,
        observable_pattern: str,
        collision: str,
    ) -> None:
        instance_id = self.host._next_id("HN")
        self.host.hard_negative_entities.update(entity_ids)
        self.host.world.hard_negative_instances.append(
            {
                "hard_negative_instance_id": instance_id,
                "scenario_type": scenario_type,
                "legitimate_reason": legitimate_reason,
                "observable_pattern": observable_pattern,
                "possible_rule_collision": collision,
                "ground_truth": "LEGITIMATE",
                "entity_ids": entity_ids,
                "transaction_ids": transaction_ids,
                "active_from": active_from,
                "active_to": active_to,
                "dataset_split": split,
            }
        )

    def _customer(
        self,
        split: str,
        segments: list[str],
        exclude: set[str] | None = None,
    ) -> str:
        blocked = set(exclude or set()) | self.host.scenario_entities | self.host.hard_negative_entities
        return self.host.choose_customer(self.rng, split, segments, blocked)

    def _customers(
        self,
        split: str,
        segments: list[str],
        count: int,
        exclude: set[str] | None = None,
    ) -> list[str]:
        blocked = set(exclude or set()) | self.host.scenario_entities | self.host.hard_negative_entities
        candidates = [
            customer_id
            for segment in segments
            for customer_id in self.host.customers_by_segment_split[(segment, split)]
            if customer_id not in blocked
        ]
        self.rng.shuffle(candidates)
        return candidates[: min(count, len(candidates))]

    def _base_time(self, split: str, max_extra_days: int) -> Any:
        start, end = self.host.split_windows[split]
        latest = max(start, end - timedelta(days=max_extra_days))
        selected = start + timedelta(days=self.rng.randint(0, max(0, (latest - start).days)))
        return self.host._event_time(selected, self.rng.randint(8, 16), self.rng)


def _split_allocation(count: int) -> list[str]:
    order = ["TRAIN", "VALIDATION", "TEST", "HIDDEN_TEST"]
    weights = [0.55, 0.15, 0.15, 0.15]
    result: list[str] = []
    for index, split in enumerate(order):
        allocated = max(1, round(count * weights[index])) if count >= 4 else 0
        result.extend([split] * allocated)
    while len(result) > count:
        result.pop()
    cursor = 0
    while len(result) < count:
        result.append(order[cursor % len(order)])
        cursor += 1
    return result
