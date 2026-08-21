"""Elliptic Feature Registry — ngữ nghĩa PHỤC HỒI theo DFRWS USA 2026.

Nguồn AUTHORITATIVE (không bịa): kho companion chính thức của bài báo
  Šafář, Pluskal, Veselý, Ryšavý — "The Enemy of Reproducibility is Opacity:
  What's Inside the Elliptic Bitcoin Dataset (and Why It Is Wrong)",
  Forensic Science International: Digital Investigation, Vol. 57, 302124, 2026.
  Repo: https://github.com/nesfit/DeanonymizedEllipticBitcoinDataset

Bài báo REVERSE-ENGINEER và validate ngữ nghĩa: 91/94 local + 60/72 aggregated =
**151/166 phục hồi**, **15 chưa giải (UNRESOLVED)**: 4, 8, 16, 113–118, 149–154.

PROVENANCE (§3): đây KHÔNG phải "tên chính thức của Elliptic" (Elliptic không
công bố). Đây là ngữ nghĩa được PHỤC HỒI & KIỂM CHỨNG bởi Šafář et al.
  * ``semantic_status = RECOVERED_AND_VALIDATED`` cho 151 đặc trưng.
  * ``semantic_status = UNRESOLVED`` cho 15 đặc trưng — giữ ẩn danh, KHÔNG bịa.
  * ``official_elliptic_semantic = False`` cho tất cả (Elliptic không xác nhận).

Giá trị trong CSV đã CHUẨN HOÁ (z-score, trừ time step) → ``value_representation``
= standardized. UI KHÔNG được hiển thị "-0.12 outputs" như số thô.

Chỉ số: kho DFRWS đánh số Feature 1..166 (1-based). Trong ma trận model, đặc
trưng thứ ``i`` (0-based) = DFRWS Feature ``i+1`` (Feature 1 = Time Step).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

N_FEATURES = 166
_SOURCE = "Šafář et al., DFRWS USA 2026 (FSI:DI Vol.57, 302124); repo nesfit/DeanonymizedEllipticBitcoinDataset"

#: Chỉ số DFRWS (1-based) CHƯA giải nghĩa — giữ ẩn danh tuyệt đối.
UNRESOLVED: frozenset[int] = frozenset({4, 8, 16, 113, 114, 115, 116, 117, 118, 149, 150, 151, 152, 153, 154})

#: Tên PHỤC HỒI verbatim từ kho companion (1-based). None = UNRESOLVED.
_NAMES: dict[int, str | None] = {
    1: "Time Step",
    2: "Transaction Volume",
    3: "Fees",
    4: None,
    5: "Number of inputs",
    6: "Number of outputs",
    7: "Number of unique input addresses",
    8: None,
    9: "Minimum of input values",
    10: "Maximum of input values",
    11: "Standard deviation of input values",
    12: "Mean of input values",
    13: "Pearson correlation between input values and indices",
    14: "Spearman correlation between input values and indices",
    15: "Number of unique output addresses",
    16: None,
    17: "Minimum of output values",
    18: "Maximum of output values",
    19: "Standard deviation of output values",
    20: "Mean of output values",
    21: "Pearson correlation between output values and indices",
    22: "Spearman correlation between output values and indices",
    23: "Minimum number of received satoshi of input addresses",
    24: "Maximum number of received satoshi of input addresses",
    25: "Standard deviation of number of received satoshi of input addresses",
    26: "Mean number of received satoshi of input addresses",
    27: "Pearson correlation between number of received satoshi of input addresses and indices",
    28: "Spearman correlation between number of received satoshi of input addresses and indices",
    29: "Minimum number of sent BTC of input addresses",
    30: "Maximum number of sent BTC of input addresses",
    31: "Standard deviation of number of sent BTC of input addresses",
    32: "Mean number of sent BTC of input addresses",
    33: "Pearson correlation between number of sent BTC of input addresses and indices",
    34: "Spearman correlation between number of sent BTC of input addresses and indices",
    35: "Minimum available BTC on input addresses",
    36: "Maximum available BTC on input addresses",
    37: "Standard deviation of available BTC on input addresses",
    38: "Mean available BTC on input addresses",
    39: "Pearson correlation between available BTC on input addresses and indices",
    40: "Spearman correlation between available BTC on input addresses and indices",
    41: "Minimum number of incoming transactions of input addresses",
    42: "Maximum number of incoming transactions of input addresses",
    43: "Standard deviation of number of incoming transactions of input addresses",
    44: "Mean number of incoming transactions of input addresses",
    45: "Pearson correlation between number of incoming transactions of input addresses and indices",
    46: "Spearman correlation between number of incoming transactions of input addresses and indices",
    47: "Minimum number of outgoing transactions of input addresses",
    48: "Maximum number of outgoing transactions of input addresses",
    49: "Standard deviation of number of outgoing transactions of input addresses",
    50: "Mean number of outgoing transactions of input addresses",
    51: "Pearson correlation between number of outgoing transactions of input addresses and indices",
    52: "Spearman correlation between number of outgoing transactions of input addresses and indices",
    53: "Minimum lifetime of input addresses",
    54: "Maximum lifetime of input addresses",
    55: "Standard deviation of lifetime of input addresses",
    56: "Mean lifetime of input addresses",
    57: "Pearson correlation between lifetime of input addresses and indices",
    58: "Spearman correlation between lifetime of input addresses and indices",
    59: "Minimum number of received satoshi of output addresses",
    60: "Maximum number of received satoshi of output addresses",
    61: "Standard deviation of number of received satoshi of output addresses",
    62: "Mean number of received satoshi of output addresses",
    63: "Pearson correlation between number of received satoshi of output addresses and indices",
    64: "Spearman correlation between number of received satoshi of output addresses and indices",
    65: "Minimum number of sent BTC of output addresses",
    66: "Maximum number of sent BTC of output addresses",
    67: "Standard deviation of number of sent BTC of output addresses",
    68: "Mean number of sent BTC of output addresses",
    69: "Pearson correlation between number of sent BTC of output addresses and indices",
    70: "Spearman correlation between number of sent BTC of output addresses and indices",
    71: "Minimum available BTC on output addresses",
    72: "Maximum available BTC on output addresses",
    73: "Standard deviation of available BTC on output addresses",
    74: "Mean available BTC on output addresses",
    75: "Pearson correlation between available BTC on output addresses and indices",
    76: "Spearman correlation between available BTC on output addresses and indices",
    77: "Minimum number of incoming transactions of output addresses",
    78: "Maximum number of incoming transactions of output addresses",
    79: "Standard deviation of number of incoming transactions of output addresses",
    80: "Mean number of incoming transactions of output addresses",
    81: "Pearson correlation between number of incoming transactions of output addresses and indices",
    82: "Spearman correlation between number of incoming transactions of output addresses and indices",
    83: "Minimum number of outgoing transactions of output addresses",
    84: "Maximum number of outgoing transactions of output addresses",
    85: "Standard deviation of number of outgoing transactions of output addresses",
    86: "Mean number of outgoing transactions of output addresses",
    87: "Pearson correlation between number of outgoing transactions of output addresses and indices",
    88: "Spearman correlation between number of outgoing transactions of output addresses and indices",
    89: "Minimum lifetime of output addresses",
    90: "Maximum lifetime of output addresses",
    91: "Standard deviation of lifetime of output addresses",
    92: "Mean lifetime of output addresses",
    93: "Pearson correlation between lifetime of output addresses and indices",
    94: "Spearman correlation between lifetime of output addresses and indices",
    95: "Minimum value of input txs",
    96: "Maximum value of input txs",
    97: "Standard deviation of value of input txs",
    98: "Mean value of input txs",
    99: "Pearson correlation between value of input txs and indices",
    100: "Spearman correlation between value of input txs and indices",
    101: "Minimum height of input txs",
    102: "Maximum height of input txs",
    103: "Standard deviation of height of input txs",
    104: "Mean height of input txs",
    105: "Pearson correlation between height of input txs and indices",
    106: "Spearman correlation between height of input txs and indices",
    107: "Minimum fee of input txs",
    108: "Maximum fee of input txs",
    109: "Standard deviation of fee of input txs",
    110: "Mean fee of input txs",
    111: "Pearson correlation between fee of input txs and indices",
    112: "Spearman correlation between fee of input txs and indices",
    113: None,
    114: None,
    115: None,
    116: None,
    117: None,
    118: None,
    119: "Minimum number of inputs of input txs",
    120: "Maximum number of inputs of input txs",
    121: "Standard deviation of number of inputs of input txs",
    122: "Mean number of inputs of input txs",
    123: "Pearson correlation between number of inputs of input txs and indices",
    124: "Spearman correlation between number of inputs of input txs and indices",
    125: "Minimum number of outputs of input txs",
    126: "Maximum number of outputs of input txs",
    127: "Standard deviation of number of outputs of input txs",
    128: "Mean number of outputs of input txs",
    129: "Pearson correlation between number of outputs of input txs and indices",
    130: "Spearman correlation between number of outputs of input txs and indices",
    131: "Minimum value of output txs",
    132: "Maximum value of output txs",
    133: "Standard deviation of value of output txs",
    134: "Mean value of output txs",
    135: "Pearson correlation between value of output txs and indices",
    136: "Spearman correlation between value of output txs and indices",
    137: "Minimum height of output txs",
    138: "Maximum height of output txs",
    139: "Standard deviation of height of output txs",
    140: "Mean height of output txs",
    141: "Pearson correlation between height of output txs and indices",
    142: "Spearman correlation between height of output txs and indices",
    143: "Minimum fee of output txs",
    144: "Maximum fee of output txs",
    145: "Standard deviation of fee of output txs",
    146: "Mean fee of output txs",
    147: "Pearson correlation between fee of output txs and indices",
    148: "Spearman correlation between fee of output txs and indices",
    149: None,
    150: None,
    151: None,
    152: None,
    153: None,
    154: None,
    155: "Minimum number of inputs of output txs",
    156: "Maximum number of inputs of output txs",
    157: "Standard deviation of number of inputs of output txs",
    158: "Mean number of inputs of output txs",
    159: "Pearson correlation between number of inputs of output txs and indices",
    160: "Spearman correlation between number of inputs of output txs and indices",
    161: "Minimum number of outputs of output txs",
    162: "Maximum number of outputs of output txs",
    163: "Standard deviation of number of outputs of output txs",
    164: "Mean number of outputs of output txs",
    165: "Pearson correlation between number of outputs of output txs and indices",
    166: "Spearman correlation between number of outputs of output txs and indices",
}


def _category(dfrws_index: int) -> str:
    """Nhóm đặc trưng theo dải chỉ số DFRWS (chỉ gán khi mapping hỗ trợ)."""
    if dfrws_index in UNRESOLVED:
        return "UNRESOLVED"
    if dfrws_index == 1:
        return "TIME"
    if dfrws_index in (2, 3, 5, 6, 7, 15):
        return "TRANSACTION_INTRINSIC"
    if 9 <= dfrws_index <= 14:
        return "INPUT_VALUE_STATS"
    if 17 <= dfrws_index <= 22:
        return "OUTPUT_VALUE_STATS"
    if 23 <= dfrws_index <= 58:
        return "INPUT_ADDRESS_HISTORY"
    if 59 <= dfrws_index <= 94:
        return "OUTPUT_ADDRESS_HISTORY"
    if 95 <= dfrws_index <= 130:
        return "UPSTREAM_TRANSACTION_AGGREGATE"
    return "DOWNSTREAM_TRANSACTION_AGGREGATE"  # 131..166


@dataclass(frozen=True)
class FeatureMeta:
    model_index: int  # 0-based trong ma trận model
    dfrws_feature: int  # 1-based theo kho DFRWS (= model_index + 1)
    display_name: str
    category: str
    value_representation: str  # count | standardized
    semantic_status: str  # RECOVERED_AND_VALIDATED | UNRESOLVED
    official_elliptic_semantic: bool  # luôn False — Elliptic không công bố
    source: str


def build_registry() -> list[FeatureMeta]:
    reg: list[FeatureMeta] = []
    for model_index in range(N_FEATURES):
        d = model_index + 1
        name = _NAMES[d]
        resolved = name is not None
        reg.append(
            FeatureMeta(
                model_index=model_index,
                dfrws_feature=d,
                display_name=name if resolved else f"Unresolved Elliptic feature #{d}",
                category=_category(d),
                value_representation="count" if d == 1 else "standardized",
                semantic_status="RECOVERED_AND_VALIDATED" if resolved else "UNRESOLVED",
                official_elliptic_semantic=False,
                source=_SOURCE,
            )
        )
    return reg


def registry_by_model_index() -> dict[int, FeatureMeta]:
    return {f.model_index: f for f in build_registry()}


def recovery_stats(reg: list[FeatureMeta] | None = None) -> dict[str, object]:
    reg = reg or build_registry()
    recovered = sum(1 for f in reg if f.semantic_status == "RECOVERED_AND_VALIDATED")
    unresolved_idx = sorted(f.dfrws_feature for f in reg if f.semantic_status == "UNRESOLVED")
    return {
        "recovered": recovered,
        "unresolved": len(reg) - recovered,
        "total": len(reg),
        "unresolved_indexes": unresolved_idx,
    }


def write_registry(path: Path) -> dict[str, object]:
    reg = build_registry()
    stats = recovery_stats(reg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "dataset": "Elliptic",
                "dataset_version": "original",
                "n_features": N_FEATURES,
                "semantic_source": _SOURCE,
                "official_elliptic_semantic": False,
                "recovered": stats["recovered"],
                "unresolved": stats["unresolved"],
                "unresolved_indexes": stats["unresolved_indexes"],
                "note": "Ngữ nghĩa PHỤC HỒI & kiểm chứng bởi Šafář et al. (DFRWS 2026), KHÔNG phải tên "
                "chính thức của Elliptic. 15 đặc trưng chưa giải giữ ẩn danh. Giá trị đã chuẩn hoá.",
                "features": [asdict(f) for f in reg],
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return stats


if __name__ == "__main__":
    print("Registry:", write_registry(Path("data/models/bitcoin_elliptic/feature_registry.json")))
