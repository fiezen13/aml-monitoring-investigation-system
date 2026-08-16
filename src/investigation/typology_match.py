"""Chọn nhóm hành vi AML cho một cảnh báo từ các tín hiệu quan sát được.

Vì sao cần file này: cả ba nơi sinh cảnh báo trong repo đều đóng dấu cứng
``T02`` — 6.541/6.541 cảnh báo hiện có đều mang cùng một nhóm hành vi. Trong khi
đó ``typologies.json`` đã mô tả sẵn điều kiện của cả mười nhóm dưới dạng
``required_signals`` và ``supporting_signals``. Luật đã có, chỉ là chưa ai chạy.

Nguyên tắc:

* **Luật nằm trong danh mục, không nằm trong code.** Hàm ở đây chỉ đối chiếu tập
  tín hiệu quan sát được với danh mục. Muốn đổi định nghĩa nhóm hành vi thì sửa
  ``typologies.json``.
* **Đủ tín hiệu bắt buộc mới được chọn.** Thiếu một tín hiệu bắt buộc là loại,
  không có chuyện "gần đúng".
* **Không khớp thì nói thẳng là không khớp.** Cột ``typology_code`` trong lược đồ
  là NOT NULL nên vẫn phải điền một mã; ta giữ ``T02`` như trước để không đổi
  hành vi cũ, nhưng đánh dấu ``is_fallback`` và ghi lý do. Chỗ nào đọc kết quả
  cũng phân biệt được "đã chứng minh" với "chưa chứng minh được".

Điểm cuối cùng ấy mới là phần quan trọng. Tác tử phản biện trong
``agents.py`` đòi bằng chứng tương ứng cho nhóm hành vi được nêu; khi cảnh báo
bị đóng dấu T02 mà không có tín hiệu ``network_flow`` nào, nó phản đối là đúng.
Đánh dấu fallback cho phép tác tử biết mình đang nhìn một giá trị mặc định chứ
không phải một kết luận.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

#: Dùng khi không tín hiệu nào đủ điều kiện. Giữ đúng giá trị mà ba nơi sinh
#: cảnh báo đang đóng dấu cứng, nên việc bật ánh xạ không làm đổi nhóm hành vi
#: của các cảnh báo vốn không có tín hiệu nào.
FALLBACK_TYPOLOGY = "T02"

#: Ngưỡng suy ra tín hiệu từ đặc trưng hành vi.
#:
#: Đây là ngưỡng vận hành, KHÔNG phải hằng số nghiệp vụ đã được thẩm định. Chúng
#: được đặt ở một chỗ và đặt tên rõ để bộ phận nghiệp vụ hiệu chỉnh, thay vì rải
#: rác dưới dạng số trần trong các câu lệnh SQL.
BEHAVIOR_SIGNAL_THRESHOLDS: dict[str, float] = {
    # Tỷ lệ tiền ra khỏi tài khoản trong vòng 2 giờ sau khi nhận.
    "rapid_outflow_ratio": 0.50,
    # Tỷ lệ đối tác chưa từng giao dịch trước mốc cửa sổ.
    "new_counterparty_ratio": 0.50,
}


@dataclass(frozen=True)
class TypologyMatch:
    """Kết quả ánh xạ, kèm đủ dấu vết để rà lại về sau."""

    typology_code: str
    pattern: str
    catalog_version: str
    observed_signals: tuple[str, ...]
    matched_required: tuple[str, ...] = field(default_factory=tuple)
    matched_supporting: tuple[str, ...] = field(default_factory=tuple)
    is_fallback: bool = False
    rationale: str = ""


@lru_cache(maxsize=1)
def _catalog() -> tuple[dict[str, Any], ...]:
    path = Path(__file__).with_name("typologies.json")
    return tuple(json.loads(path.read_text(encoding="utf-8")))


def match_typology(signals: set[str] | frozenset[str]) -> TypologyMatch:
    """Chọn nhóm hành vi khớp nhất với tập tín hiệu đã quan sát.

    Xếp hạng: nhiều tín hiệu bắt buộc hơn thắng trước; hoà thì xét tín hiệu hỗ
    trợ; hoà tiếp thì lấy mã nhỏ hơn để kết quả tất định giữa các lần chạy.
    """
    observed = tuple(sorted(signals))
    candidates: list[tuple[int, int, str, dict[str, Any], tuple[str, ...], tuple[str, ...]]] = []

    for entry in _catalog():
        required = tuple(entry.get("required_signals") or ())
        # Nhóm không khai tín hiệu bắt buộc thì không thể chứng minh bằng dữ
        # liệu — bỏ qua, đừng để nó thắng chỉ vì điều kiện rỗng.
        if not required or not all(signal in signals for signal in required):
            continue
        supporting = tuple(s for s in (entry.get("supporting_signals") or ()) if s in signals)
        candidates.append((len(required), len(supporting), entry["typology_code"], entry, required, supporting))

    if not candidates:
        return TypologyMatch(
            typology_code=FALLBACK_TYPOLOGY,
            pattern=pattern_of(FALLBACK_TYPOLOGY),
            catalog_version=version_of(FALLBACK_TYPOLOGY),
            observed_signals=observed,
            is_fallback=True,
            rationale=(
                "Không tín hiệu quan sát được nào đủ điều kiện bắt buộc của bất kỳ nhóm hành vi nào; "
                f"dùng mặc định {FALLBACK_TYPOLOGY}. Đây là giá trị mặc định, không phải kết luận."
            ),
        )

    # Sắp giảm dần theo số tín hiệu, tăng dần theo mã để phá hoà tất định.
    best = sorted(candidates, key=lambda item: (-item[0], -item[1], item[2]))[0]
    _, _, code, entry, required, supporting = best
    return TypologyMatch(
        typology_code=code,
        pattern=entry["pattern"],
        catalog_version=str(entry.get("version", "v1")),
        observed_signals=observed,
        matched_required=required,
        matched_supporting=supporting,
        is_fallback=False,
        rationale=(
            f"Khớp đủ {len(required)} tín hiệu bắt buộc ({', '.join(required)})"
            + (f" và {len(supporting)} tín hiệu hỗ trợ ({', '.join(supporting)})" if supporting else "")
            + "."
        ),
    )


def entry_of(code: str) -> dict[str, Any]:
    for entry in _catalog():
        if entry["typology_code"] == code:
            return entry
    raise LookupError(f"Nhóm hành vi {code} không có trong danh mục")


def pattern_of(code: str) -> str:
    return str(entry_of(code)["pattern"])


def version_of(code: str) -> str:
    return str(entry_of(code).get("version", "v1"))


def signals_from_behavior(features: Mapping[str, Any]) -> set[str]:
    """Suy tín hiệu từ đặc trưng hành vi của một tài khoản.

    Chỉ phát ra tín hiệu mà dữ liệu thật sự chứng minh được. Đặc trưng vắng mặt
    thì không phát tín hiệu — không suy đoán, không lấy giá trị mặc định.
    """
    signals: set[str] = set()

    rapid = _number(features.get("rapid_outflow_ratio"))
    if rapid is not None and rapid >= BEHAVIOR_SIGNAL_THRESHOLDS["rapid_outflow_ratio"]:
        signals.add("rapid_outflow")

    new_ratio = _number(features.get("new_counterparty_ratio"))
    if new_ratio is not None and new_ratio >= BEHAVIOR_SIGNAL_THRESHOLDS["new_counterparty_ratio"]:
        signals.add("new_counterparties")

    return signals


def signals_from_graph_motifs(motifs: Mapping[str, Any]) -> set[str]:
    """Suy tín hiệu từ số lần trúng mẫu hình của bộ phát hiện đồ thị.

    Các khoá này do ``scripts/load_fusion_release.py`` ghi vào
    ``behavior_feature_snapshot.features``. Chỉ nhận khi bộ phát hiện đồ thị
    thật sự báo trúng — đúng nguyên tắc "không khẳng định mẫu hình khi bộ phát
    hiện không có bằng chứng".
    """
    signals: set[str] = set()
    if _count(motifs.get("fan_in_hit")):
        signals.add("fan_in")
    if _count(motifs.get("fan_out_hit")):
        signals.add("fan_out")
    if _count(motifs.get("cycle_hit")):
        signals.add("directed_cycle")
    if _count(motifs.get("gather_scatter_hit")):
        # Gom rồi rải qua tài khoản trung gian chính là dòng chảy mạng lưới mà
        # T02 đòi hỏi. Đây là tín hiệu duy nhất chứng minh được T02 từ dữ liệu.
        signals.add("network_flow")
    return signals


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # loại NaN


def _count(value: Any) -> bool:
    number = _number(value)
    return number is not None and number > 0
