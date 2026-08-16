"""Gán nhóm hành vi hàng loạt cho các bản phát hành nạp bằng psycopg.

``src/services/if_alert_publish.py`` lo đường ghi từng cảnh báo qua SQLAlchemy.
Hai script nạp bản phát hành (``load_fusion_release.py``,
``load_currency_native_edge_release.py``) lại chèn hàng loạt bằng psycopg thô,
nên cần một đường riêng — nhưng vẫn phải dùng **chung một bộ luật** trong
``src/investigation/typology_match.py``. Đó là lý do file này không chứa luật
nào của riêng nó.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from src.investigation.typology_match import (
    FALLBACK_TYPOLOGY,
    TypologyMatch,
    match_typology,
    pattern_of,
    signals_from_graph_motifs,
    version_of,
)

_UPSERT_MATCH = """
INSERT INTO alert_typology_match (
    alert_id, typology_code, pattern, catalog_version,
    observed_signals, matched_required, matched_supporting,
    is_fallback, rationale
) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
ON CONFLICT (alert_id) DO UPDATE SET
    typology_code = EXCLUDED.typology_code,
    pattern = EXCLUDED.pattern,
    catalog_version = EXCLUDED.catalog_version,
    observed_signals = EXCLUDED.observed_signals,
    matched_required = EXCLUDED.matched_required,
    matched_supporting = EXCLUDED.matched_supporting,
    is_fallback = EXCLUDED.is_fallback,
    rationale = EXCLUDED.rationale
"""


def _match_row(match: TypologyMatch, alert_id: str) -> tuple[Any, ...]:
    return (
        alert_id,
        match.typology_code,
        match.pattern,
        match.catalog_version,
        json.dumps(list(match.observed_signals)),
        json.dumps(list(match.matched_required)),
        json.dumps(list(match.matched_supporting)),
        match.is_fallback,
        match.rationale,
    )


def apply_matches(pg: Any, matches: Sequence[tuple[str, TypologyMatch]]) -> dict[str, int]:
    """Ghi mã nhóm hành vi vào ``alert`` và dấu vết vào ``alert_typology_match``.

    Chỉ cập nhật ``alert.typology_code`` cho những cảnh báo có ánh xạ thật; ánh
    xạ mặc định không được phép ghi đè lên mã mà chỗ khác đã đặt có căn cứ.
    """
    if not matches:
        return {"matched": 0, "fallback": 0}

    with pg.cursor() as cur:
        cur.executemany(_UPSERT_MATCH, [_match_row(match, alert_id) for alert_id, match in matches])
        derived = [(match.typology_code, alert_id) for alert_id, match in matches if not match.is_fallback]
        if derived:
            cur.executemany("UPDATE alert SET typology_code = %s WHERE alert_id = %s", derived)

    return {
        "matched": sum(1 for _, match in matches if not match.is_fallback),
        "fallback": sum(1 for _, match in matches if match.is_fallback),
    }


def assign_from_graph_motifs(pg: Any, rows: Iterable[tuple[str, Mapping[str, Any]]]) -> dict[str, int]:
    """Suy nhóm hành vi từ số lần trúng mẫu hình của bộ phát hiện đồ thị."""
    matches = [(alert_id, match_typology(signals_from_graph_motifs(motifs))) for alert_id, motifs in rows]
    return apply_matches(pg, matches)


def record_fallback(pg: Any, alert_ids: Iterable[str], *, reason: str) -> dict[str, int]:
    """Ghi nhận rõ ràng rằng một lô cảnh báo mang nhóm hành vi mặc định.

    Dùng cho bản phát hành không có tín hiệu hành vi nào để đối chiếu — ví dụ mô
    hình chấm điểm ở mức giao dịch. Ghi ra vẫn tốt hơn im lặng: câu truy vấn
    ``WHERE is_fallback`` cho biết đúng phần bề mặt chưa được chứng minh.
    """
    match = TypologyMatch(
        typology_code=FALLBACK_TYPOLOGY,
        pattern=pattern_of(FALLBACK_TYPOLOGY),
        catalog_version=version_of(FALLBACK_TYPOLOGY),
        observed_signals=(),
        is_fallback=True,
        rationale=reason,
    )
    return apply_matches(pg, [(alert_id, match) for alert_id in alert_ids])
