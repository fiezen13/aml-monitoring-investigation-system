"""Five configurable, causal AML benchmark scenario modules."""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

from abm.models import money


class ScenarioEngine:
    def __init__(self, host: Any, rng: random.Random) -> None:
        self.host = host
        self.rng = rng
        self.quotas = host.registry.value("AML_SCENARIO_QUOTAS_001")

    def generate(self) -> None:
        handlers: dict[str, Callable[[str], None]] = {
            "STRUCTURING": self._structuring,
            "RAPID_PASS_THROUGH": self._rapid_pass_through,
            "MULE_FUNNEL": self._mule_funnel,
            "FAN_IN_FAN_OUT": self._fan_in_fan_out,
            "CIRCULAR_LAYERING": self._circular_layering,
        }
        for scenario_type, configured_count in self.quotas.items():
            count = max(1, round(int(configured_count) * self.host.config.scenario_scale))
            for split in _split_allocation(count):
                handlers[scenario_type](split)

    def _structuring(self, split: str) -> None:
        params = self.host.registry.value("AML_STRUCTURING_001")
        actor = self._customer(split, ["HOUSEHOLD", "HOUSEHOLD_BUSINESS", "SME"])
        account = self.host.primary_account_by_customer[actor]
        instance_id, network_id = self._start_instance("STRUCTURING", split)
        base = self._base_time(split, int(params["episode_days"][1]) + 2)
        count = self.rng.randint(int(params["deposit_count"][0]), int(params["deposit_count"][1]))
        threshold = Decimal(str(params["benchmark_threshold_vnd"]))
        low, high = map(Decimal, map(str, params["amount_fraction"]))
        transaction_ids: list[str] = []
        total = Decimal("0")
        for index in range(count):
            amount = money(threshold * Decimal(str(self.rng.uniform(float(low), float(high)))))
            total += amount
            transaction_id = self.host.add_transaction(
                event_time=base + timedelta(hours=index * self.rng.uniform(3, 10)),
                source_counterparty_ref=self.host.external_ref(actor, "CASH_DEPOSITOR", index),
                destination_account_id=account,
                amount=amount,
                transaction_type="CASH_DEPOSIT",
                channel=self.rng.choice(["BRANCH", "ATM"]),
                customer_id=actor,
                dataset_split=split,
                purpose_code="CASH_DEPOSIT",
                purpose_text="Cash deposit",
            )
            self._label_tx(transaction_id, instance_id, network_id, "PLACEMENT", split)
            transaction_ids.append(str(transaction_id))
        delay = self.rng.uniform(
            float(params["consolidation_delay_hours"][0]), float(params["consolidation_delay_hours"][1])
        )
        outgoing = self.host.add_transaction(
            event_time=base + timedelta(hours=count * 8 + delay),
            source_account_id=account,
            destination_counterparty_ref=self.host.external_ref(actor, "CONTROLLER"),
            amount=money(total * Decimal("0.96")),
            transaction_type="TRANSFER",
            channel="INTERNET",
            customer_id=actor,
            dataset_split=split,
            purpose_code="CONSOLIDATION",
            purpose_text="Funds transfer",
        )
        self._label_tx(outgoing, instance_id, network_id, "CONSOLIDATION", split)
        self._finish_instance(
            instance_id,
            network_id,
            "STRUCTURING",
            split,
            base,
            base + timedelta(days=7),
            [actor],
            transaction_ids + [str(outgoing)],
        )
        self._role(actor, instance_id, network_id, "STRUCTURER", base, base + timedelta(days=7), split)

    def _rapid_pass_through(self, split: str) -> None:
        params = self.host.registry.value("AML_RAPID_PASS_THROUGH_001")
        actor = self._customer(split, ["SALARIED", "HOUSEHOLD", "STUDENT"])
        account = self.host.primary_account_by_customer[actor]
        instance_id, network_id = self._start_instance("RAPID_PASS_THROUGH", split)
        base = self._base_time(split, 2)
        incoming_count = self.rng.randint(int(params["incoming_count"][0]), int(params["incoming_count"][1]))
        retained = Decimal(
            str(self.rng.uniform(float(params["retained_fraction"][0]), float(params["retained_fraction"][1])))
        )
        transaction_ids: list[str] = []
        total = Decimal("0")
        for index in range(incoming_count):
            amount = money(self.rng.uniform(25000000, 140000000))
            total += amount
            incoming = self.host.add_transaction(
                event_time=base + timedelta(minutes=index * 7),
                source_counterparty_ref=self.host.external_ref(actor, "ORIGINATOR", index),
                destination_account_id=account,
                amount=amount,
                transaction_type="TRANSFER",
                channel="MOBILE",
                customer_id=actor,
                dataset_split=split,
                purpose_code="TRANSFER",
                purpose_text="Incoming transfer",
            )
            self._label_tx(incoming, instance_id, network_id, "COLLECTION", split)
            transaction_ids.append(str(incoming))
        dwell = self.rng.randint(int(params["dwell_minutes"][0]), int(params["dwell_minutes"][1]))
        outgoing = self.host.add_transaction(
            event_time=base + timedelta(minutes=dwell),
            source_account_id=account,
            destination_counterparty_ref=self.host.external_ref(actor, "CONTROLLER"),
            amount=money(total * (Decimal("1") - retained)),
            transaction_type="TRANSFER",
            channel="MOBILE",
            customer_id=actor,
            dataset_split=split,
            purpose_code="TRANSFER",
            purpose_text="Outgoing transfer",
        )
        self._label_tx(outgoing, instance_id, network_id, "PASS_THROUGH", split)
        end = base + timedelta(minutes=dwell + 5)
        self._finish_instance(
            instance_id, network_id, "RAPID_PASS_THROUGH", split, base, end, [actor], transaction_ids + [str(outgoing)]
        )
        self._role(actor, instance_id, network_id, "PASS_THROUGH_ACCOUNT", base, end, split)

    def _mule_funnel(self, split: str) -> None:
        params = self.host.registry.value("AML_MULE_FUNNEL_001")
        mule_count = self.rng.randint(int(params["mules"][0]), int(params["mules"][1]))
        mules = self._customers(split, ["SALARIED", "HOUSEHOLD", "STUDENT"], mule_count)
        collector = self._customer(split, ["HOUSEHOLD_BUSINESS", "SME"], exclude=set(mules))
        actors = [*mules, collector]
        instance_id, network_id = self._start_instance("MULE_FUNNEL", split)
        base = self._base_time(split, 4)
        transaction_ids: list[str] = []
        collector_total = Decimal("0")
        for mule_index, mule in enumerate(mules):
            mule_account = self.host.primary_account_by_customer[mule]
            amount = money(self.rng.uniform(35000000, 120000000))
            incoming = self.host.add_transaction(
                event_time=base + timedelta(minutes=mule_index * 18),
                source_counterparty_ref=self.host.external_ref(mule, "SCAM_VICTIM", mule_index),
                destination_account_id=mule_account,
                amount=amount,
                transaction_type="TRANSFER",
                channel="MOBILE",
                customer_id=mule,
                dataset_split=split,
                purpose_code="TRANSFER",
                purpose_text="Incoming transfer",
            )
            self._label_tx(incoming, instance_id, network_id, "COLLECTION", split)
            transaction_ids.append(str(incoming))
            retained = Decimal(
                str(self.rng.uniform(float(params["retained_fraction"][0]), float(params["retained_fraction"][1])))
            )
            forwarded_amount = money(amount * (Decimal("1") - retained))
            collector_total += forwarded_amount
            dwell = self.rng.randint(int(params["dwell_minutes"][0]), int(params["dwell_minutes"][1]))
            forwarded = self.host.add_transaction(
                event_time=base + timedelta(minutes=mule_index * 18 + dwell),
                source_account_id=mule_account,
                destination_account_id=self.host.primary_account_by_customer[collector],
                amount=forwarded_amount,
                transaction_type="TRANSFER",
                channel="MOBILE",
                customer_id=mule,
                dataset_split=split,
                purpose_code="TRANSFER",
                purpose_text="Funds transfer",
            )
            self._label_tx(forwarded, instance_id, network_id, "MULE_FORWARD", split)
            transaction_ids.append(str(forwarded))
        payout = self.host.add_transaction(
            event_time=base + timedelta(days=2),
            source_account_id=self.host.primary_account_by_customer[collector],
            destination_counterparty_ref=self.host.external_ref(collector, "NETWORK_CONTROLLER"),
            amount=money(collector_total * Decimal("0.97")),
            transaction_type="TRANSFER",
            channel="INTERNET",
            customer_id=collector,
            dataset_split=split,
            purpose_code="SETTLEMENT",
            purpose_text="Settlement transfer",
        )
        self._label_tx(payout, instance_id, network_id, "CONSOLIDATION", split)
        transaction_ids.append(str(payout))

        if len(mules) >= 2 and self.rng.random() < float(params["shared_device_probability"]):
            shared_device = self._ensure_device(mules[0])
            if shared_device not in self.host.devices_by_customer[mules[1]]:
                self.host.devices_by_customer[mules[1]].append(shared_device)
            self.host.add_relationship(
                source_type="CUSTOMER",
                source_id=mules[0],
                target_type="CUSTOMER",
                target_id=mules[1],
                relationship_type="SHARED_DEVICE",
                direction="UNDIRECTED",
                method="PROBABILISTIC",
                confidence=0.88,
                valid_from=base,
                dataset_split=split,
                inference_logic=f"Repeated use of tokenized device {shared_device} across mule accounts.",
                observation_count=7,
            )
        end = base + timedelta(days=3)
        self._finish_instance(instance_id, network_id, "MULE_FUNNEL", split, base, end, actors, transaction_ids)
        for mule in mules:
            self._role(mule, instance_id, network_id, "MULE", base, end, split)
        self._role(collector, instance_id, network_id, "COLLECTOR", base, end, split)
        self.host.world.hidden_relationships.append(
            {
                "hidden_relationship_id": self.host._next_id("HREL"),
                "scenario_instance_id": instance_id,
                "network_id": network_id,
                "source_entity_id": collector,
                "target_entity_ids": mules,
                "relationship_type": "TRUE_COORDINATION",
                "true_controller_id": collector,
                "active_from": base,
                "active_to": end,
                "dataset_split": split,
            }
        )

    def _fan_in_fan_out(self, split: str) -> None:
        params = self.host.registry.value("AML_FAN_IN_FAN_OUT_001")
        hub = self._customer(split, ["HOUSEHOLD", "HOUSEHOLD_BUSINESS", "SME"])
        hub_account = self.host.primary_account_by_customer[hub]
        instance_id, network_id = self._start_instance("FAN_IN_FAN_OUT", split)
        base = self._base_time(split, 4)
        fan_in = self.rng.randint(int(params["fan_in"][0]), int(params["fan_in"][1]))
        fan_out = self.rng.randint(int(params["fan_out"][0]), int(params["fan_out"][1]))
        transaction_ids: list[str] = []
        total = Decimal("0")
        for index in range(fan_in):
            amount = money(self.rng.uniform(8000000, 55000000))
            total += amount
            incoming = self.host.add_transaction(
                event_time=base + timedelta(minutes=index * self.rng.randint(3, 14)),
                source_counterparty_ref=self.host.external_ref(hub, "COLLECTION_SOURCE", index),
                destination_account_id=hub_account,
                amount=amount,
                transaction_type="TRANSFER",
                channel="MOBILE",
                customer_id=hub,
                dataset_split=split,
                purpose_code="TRANSFER",
                purpose_text="Incoming payment",
            )
            self._label_tx(incoming, instance_id, network_id, "FAN_IN", split)
            transaction_ids.append(str(incoming))
        retained = Decimal(
            str(self.rng.uniform(float(params["retained_fraction"][0]), float(params["retained_fraction"][1])))
        )
        distributable = total * (Decimal("1") - retained)
        for index in range(fan_out):
            outgoing = self.host.add_transaction(
                event_time=base + timedelta(hours=8, minutes=index * 11),
                source_account_id=hub_account,
                destination_counterparty_ref=self.host.external_ref(hub, "DISBURSEMENT", index),
                amount=money(distributable / Decimal(str(fan_out))),
                transaction_type="TRANSFER",
                channel="INTERNET",
                customer_id=hub,
                dataset_split=split,
                purpose_code="DISBURSEMENT",
                purpose_text="Outgoing payment",
            )
            self._label_tx(outgoing, instance_id, network_id, "FAN_OUT", split)
            transaction_ids.append(str(outgoing))
        end = base + timedelta(days=1)
        self._finish_instance(instance_id, network_id, "FAN_IN_FAN_OUT", split, base, end, [hub], transaction_ids)
        self._role(hub, instance_id, network_id, "COLLECTION_HUB", base, end, split)

    def _circular_layering(self, split: str) -> None:
        params = self.host.registry.value("AML_CIRCULAR_LAYERING_001")
        ring_size = self.rng.randint(int(params["ring_size"][0]), int(params["ring_size"][1]))
        ring = self._customers(split, ["SALARIED", "HOUSEHOLD", "HOUSEHOLD_BUSINESS", "SME"], ring_size)
        instance_id, network_id = self._start_instance("CIRCULAR_LAYERING", split)
        base = self._base_time(split, 5)
        initial_amount = money(self.rng.uniform(180000000, 850000000))
        transaction_ids: list[str] = []
        funding = self.host.add_transaction(
            event_time=base,
            source_counterparty_ref=self.host.external_ref(ring[0], "ILLICIT_SOURCE"),
            destination_account_id=self.host.primary_account_by_customer[ring[0]],
            amount=initial_amount,
            transaction_type="TRANSFER",
            channel="BRANCH",
            customer_id=ring[0],
            dataset_split=split,
            purpose_code="TRANSFER",
            purpose_text="Incoming transfer",
        )
        self._label_tx(funding, instance_id, network_id, "ENTRY", split)
        transaction_ids.append(str(funding))
        current_amount = initial_amount
        event_time = base + timedelta(hours=3)
        rounds = self.rng.randint(int(params["rounds"][0]), int(params["rounds"][1]))
        for round_index in range(rounds):
            for hop_index, sender in enumerate(ring):
                receiver = ring[(hop_index + 1) % len(ring)]
                retention = Decimal(
                    str(
                        self.rng.uniform(
                            float(params["retained_fraction_per_hop"][0]), float(params["retained_fraction_per_hop"][1])
                        )
                    )
                )
                current_amount = money(current_amount * (Decimal("1") - retention))
                dwell = self.rng.randint(int(params["dwell_minutes"][0]), int(params["dwell_minutes"][1]))
                event_time += timedelta(minutes=dwell)
                transaction_id = self.host.add_transaction(
                    event_time=event_time,
                    source_account_id=self.host.primary_account_by_customer[sender],
                    destination_account_id=self.host.primary_account_by_customer[receiver],
                    amount=current_amount,
                    transaction_type="TRANSFER",
                    channel=self.rng.choice(["MOBILE", "INTERNET"]),
                    customer_id=sender,
                    dataset_split=split,
                    purpose_code="TRANSFER",
                    purpose_text="Funds transfer",
                )
                self._label_tx(transaction_id, instance_id, network_id, f"LAYER_{round_index + 1}", split)
                transaction_ids.append(str(transaction_id))
        end = event_time + timedelta(minutes=1)
        self._finish_instance(instance_id, network_id, "CIRCULAR_LAYERING", split, base, end, ring, transaction_ids)
        for index, actor in enumerate(ring):
            self._role(actor, instance_id, network_id, "RING_MEMBER" if index else "COORDINATOR", base, end, split)
        self.host.world.hidden_relationships.append(
            {
                "hidden_relationship_id": self.host._next_id("HREL"),
                "scenario_instance_id": instance_id,
                "network_id": network_id,
                "source_entity_id": ring[0],
                "target_entity_ids": ring[1:],
                "relationship_type": "TRUE_COORDINATION",
                "true_controller_id": ring[0],
                "active_from": base,
                "active_to": end,
                "dataset_split": split,
            }
        )

    def _start_instance(self, scenario_type: str, split: str) -> tuple[str, str]:
        instance_id = self.host._next_id("SCN")
        network_id = self.host._next_id("NET")
        self.host.world.networks.append(
            {
                "network_id": network_id,
                "scenario_instance_id": instance_id,
                "scenario_type": scenario_type,
                "network_type": "SYNTHETIC_AML_TYPOLOGY",
                "dataset_split": split,
            }
        )
        return instance_id, network_id

    def _finish_instance(
        self,
        instance_id: str,
        network_id: str,
        scenario_type: str,
        split: str,
        active_from: Any,
        active_to: Any,
        actors: list[str],
        transaction_ids: list[str],
    ) -> None:
        self.host.scenario_entities.update(actors)
        self.host.world.scenario_instances.append(
            {
                "scenario_instance_id": instance_id,
                "scenario_type": scenario_type,
                "network_id": network_id,
                "benchmark_insertion": True,
                "prevalence_claim": False,
                "active_from": active_from,
                "active_to": active_to,
                "actor_count": len(actors),
                "transaction_count": len(transaction_ids),
                "dataset_split": split,
                "parameter_registry_version": self.host.registry.version,
            }
        )
        self.host.world.hidden_actions.append(
            {
                "hidden_action_id": self.host._next_id("HACT"),
                "scenario_instance_id": instance_id,
                "network_id": network_id,
                "scenario_type": scenario_type,
                "true_actor_ids": actors,
                "transaction_ids": transaction_ids,
                "hidden_intent": "SYNTHETIC_LAUNDERING_BENCHMARK",
                "causal_start_time": active_from,
                "causal_end_time": active_to,
                "dataset_split": split,
            }
        )

    def _role(
        self,
        customer_id: str,
        instance_id: str,
        network_id: str,
        role: str,
        active_from: Any,
        active_to: Any,
        split: str,
    ) -> None:
        self.host.record_entity_label(
            entity_id=customer_id,
            entity_type="CUSTOMER",
            scenario_instance_id=instance_id,
            network_id=network_id,
            role=role,
            active_from=active_from,
            active_to=active_to,
            dataset_split=split,
        )
        account_id = self.host.primary_account_by_customer[customer_id]
        self.host.record_entity_label(
            entity_id=account_id,
            entity_type="ACCOUNT",
            scenario_instance_id=instance_id,
            network_id=network_id,
            role=role,
            active_from=active_from,
            active_to=active_to,
            dataset_split=split,
        )

    def _label_tx(self, transaction_id: str | None, instance_id: str, network_id: str, stage: str, split: str) -> None:
        self.host.record_transaction_label(transaction_id, instance_id, network_id, stage, split)

    def _customer(
        self,
        split: str,
        segments: list[str],
        exclude: set[str] | None = None,
    ) -> str:
        blocked = set(exclude or set()) | self.host.scenario_entities | self.host.hard_negative_entities
        return self.host.choose_customer(self.rng, split, segments, blocked)

    def _customers(self, split: str, segments: list[str], count: int) -> list[str]:
        blocked = self.host.scenario_entities | self.host.hard_negative_entities
        candidates = [
            customer_id
            for segment in segments
            for customer_id in self.host.customers_by_segment_split[(segment, split)]
            if customer_id not in blocked
        ]
        self.rng.shuffle(candidates)
        if len(candidates) < count:
            raise ValueError(f"not enough scenario candidates for {split}: need {count}, found {len(candidates)}")
        return candidates[:count]

    def _base_time(self, split: str, max_extra_days: int) -> Any:
        start, end = self.host.split_windows[split]
        latest = max(start, end - timedelta(days=max_extra_days))
        selected = start + timedelta(days=self.rng.randint(0, max(0, (latest - start).days)))
        return self.host._event_time(selected, self.rng.randint(7, 13), self.rng)

    def _ensure_device(self, customer_id: str) -> str:
        devices = self.host.devices_by_customer[customer_id]
        if devices:
            return devices[0]
        device_id = self.host._next_id("DEV")
        customer = self.host.customer_by_id[customer_id]
        first_seen = self.host.config.simulation_start.astimezone(self.host.release_time.tzinfo)
        self.host.world.devices.append(
            {
                "schema_version": "1.0",
                "device_id": device_id,
                "source_system": "abm-bank-device-tokenizer",
                "source_record_id": device_id,
                "device_type": "MOBILE_APP",
                "os_family": "ANDROID",
                "first_seen_at": first_seen,
                "last_seen_at": self.host.config.simulation_end.astimezone(first_seen.tzinfo),
                "is_rooted_or_emulator": False,
                "created_at": self.host.release_time,
                "valid_from": first_seen,
                "valid_to": None,
                "entity_split": customer["entity_split"],
                "data_class": "C3_RESTRICTED",
            }
        )
        devices.append(device_id)
        return device_id


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
