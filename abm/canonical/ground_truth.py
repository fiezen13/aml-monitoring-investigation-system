"""Phase 13 — ground truth, in a physically separate subtree.

Bank View and Ground Truth are different directories, not different columns with
a naming convention. A directory boundary is enforceable by a test; a convention
is enforceable by hope.

## What is preserved and where it comes from

| Table | Source |
|---|---|
| `entity_labels` | IBM `is_laundering`, lifted to the account and owner |
| `transaction_labels` | IBM `is_laundering`, per transaction, with scenario stage |
| `scenario_instances` | IBM `HI-Medium_Patterns.txt` — 8 named typologies |
| `criminal_networks` | Membership of those pattern instances, with roles |
| `hard_negative_instances` | Phase 15, labelled `LEGITIMATE` |
| `split_assignments` | Phase 16 |

Nothing here is invented. The typologies are IBM's names, the network membership
is IBM's grouping, and the labels are IBM's labels. Roles are the one derived
field, inferred from each account's position in its instance's flow.

## The claim this does not make

`prevalence_claim: false` in the manifest. Scenario counts are benchmark coverage
decisions. A 150-instance release says nothing about how much laundering a
Vietnamese bank sees, and the ratio of flagged to unflagged entities here is an
artifact of subgraph selection — the release seeds on laundering patterns, which
concentrates them far above any real base rate.
"""

from __future__ import annotations

from typing import Any

SCENARIO_ID_FORMAT = "SCN-{:06d}"
NETWORK_ID_FORMAT = "NET-{:06d}"

# Where an account sits in its instance's flow. Derived from in/out degree
# within the instance only, never from anything outside it.
ROLES = ("ORIGINATOR", "PASSTHROUGH", "BENEFICIARY", "ISOLATED")


def infer_roles(instance_edges: list[tuple[str, str]]) -> dict[str, str]:
    """Assign a role to each account from its degree inside one instance.

    An account that only sends is where value enters the pattern; one that only
    receives is where it lands; one that does both is a conduit. This is
    structural and says nothing about intent, which is why the column is named
    for position rather than culpability.
    """
    outgoing: dict[str, int] = {}
    incoming: dict[str, int] = {}
    for source, destination in instance_edges:
        outgoing[source] = outgoing.get(source, 0) + 1
        incoming[destination] = incoming.get(destination, 0) + 1

    roles = {}
    for account in set(outgoing) | set(incoming):
        sends = outgoing.get(account, 0)
        receives = incoming.get(account, 0)
        if sends and receives:
            roles[account] = "PASSTHROUGH"
        elif sends:
            roles[account] = "ORIGINATOR"
        elif receives:
            roles[account] = "BENEFICIARY"
        else:
            roles[account] = "ISOLATED"
    return roles


def build_entity_labels(
    accounts: list[dict[str, Any]],
    flagged_accounts: set[str],
    window_start: str,
    window_end: str,
) -> list[dict[str, Any]]:
    """Account-level and owner-level involvement labels.

    An account is labelled when any transaction touching it is flagged. The owner
    inherits it, because a customer whose account is involved is involved — but
    the two are separate rows so a consumer can choose its prediction target
    rather than having one chosen for it.
    """
    rows = []
    owners_flagged: dict[str, str] = {}
    for account in accounts:
        involved = account["account_id"] in flagged_accounts
        rows.append(
            {
                "entity_id": account["account_id"],
                "entity_type": "ACCOUNT",
                "label_type": "IBM_AML_INVOLVEMENT",
                "label_value": int(involved),
                "active_from": window_start,
                "active_to": window_end,
                "source": "IBM_AML",
            }
        )
        if involved:
            owners_flagged[account["owner_id"]] = account["owner_type"]

    for owner_id, owner_type in sorted(owners_flagged.items()):
        rows.append(
            {
                "entity_id": owner_id,
                "entity_type": owner_type,
                "label_type": "IBM_AML_INVOLVEMENT",
                "label_value": 1,
                "active_from": window_start,
                "active_to": window_end,
                "source": "IBM_AML",
            }
        )
    return rows


def build_scenario_instances(selected: list[dict[str, Any]], splits: dict[str, str]) -> list[dict[str, Any]]:
    """One row per IBM pattern instance carried into the release."""
    return [
        {
            "scenario_id": entry["scenario_id"],
            "network_id": entry["network_id"],
            "typology": entry["typology"],
            "typology_parameter": entry["typology_parameter"],
            "transaction_count": entry["transaction_count"],
            "account_count": entry["account_count"],
            "first_event": entry["first_event"],
            "last_event": entry["last_event"],
            "split": splits.get(entry["scenario_id"], "TRAIN"),
            "benchmark_quota": True,
            "prevalence_claim": False,
            "source": "IBM_PATTERNS",
        }
        for entry in selected
    ]


def build_criminal_networks(
    selected: list[dict[str, Any]], account_lookup: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Network membership with a structural role per member."""
    rows = []
    for entry in selected:
        roles = infer_roles(entry["edges"])
        for account_key, role in sorted(roles.items()):
            account = account_lookup.get(account_key)
            if account is None:
                continue
            rows.append(
                {
                    "network_id": entry["network_id"],
                    "scenario_id": entry["scenario_id"],
                    "member_entity_id": account["account_id"],
                    "member_entity_type": "ACCOUNT",
                    "owner_entity_id": account["owner_id"],
                    "owner_entity_type": account["owner_type"],
                    "true_role": role,
                    "source": "IBM_PATTERNS",
                }
            )
    return rows


def build_hard_negative_instances(episodes: list[Any], splits: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "hard_negative_id": episode.hard_negative_id,
            "family": episode.family,
            "entity_id": episode.entity_id,
            "entity_type": episode.entity_type,
            "account_id": episode.account_id,
            "transaction_count": len(episode.legs),
            "legitimate_explanation": episode.explanation,
            "observable_collision": episode.collision,
            "ground_truth": "LEGITIMATE",
            "split": splits.get(episode.entity_id, "TRAIN"),
            "source": "P022_SIMULATION",
        }
        for episode in episodes
    ]
