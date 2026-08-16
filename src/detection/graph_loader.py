"""Nạp bằng chứng của bộ phát hiện đồ thị vào PostgreSQL.

Ba detector FAN / GATHER_SCATTER / CYCLE đã chạy ngoại tuyến và để lại
``graph_handoff/graph_evidence_v1.jsonl``. File đó dùng ``source_transaction_id``
(mã băm trong bộ dữ liệu gốc), còn PostgreSQL đánh số giao dịch bằng ``bigint``.
Không dịch mã thì mọi cạnh trong bằng chứng đều trỏ vào hư không.

**Đây là chỗ dễ sai nhất và cũng là chỗ có chốt chặn nghiêm nhất.** Tác tử phản
biện đối chiếu từng cạnh với bảng ``transaction``: nếu ``from``/``to`` không
khớp đúng giao dịch được trích dẫn, cả phiên điều tra bị đánh trượt
(``MISSING_SOURCE_RECORD``). Nên bộ nạp này:

* dịch mã giao dịch qua ``source_transaction_id``;
* đối chiếu hai đầu tài khoản của từng cạnh với chính bản ghi giao dịch;
* **loại cả bản ghi bằng chứng** nếu có bất kỳ cạnh nào không khớp — nạp một
  nửa còn tệ hơn không nạp, vì nó tạo ra bằng chứng trông hợp lệ mà sai.

Việc dịch mã và đối chiếu làm bằng SQL trên bảng tạm, không phải bằng vòng lặp
Python: một lô có hàng triệu cạnh.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("fin07.graph_loader")

DEFAULT_EVIDENCE = Path("graph_handoff/graph_evidence_v1.jsonl")

#: Mẫu hình mà danh mục nhóm hành vi hiểu được. Bản ghi mang mẫu hình ngoài danh
#: sách này vẫn nạp, nhưng sẽ không chọn được nhóm hành vi nào.
KNOWN_PATTERNS = frozenset({"FAN_IN", "FAN_OUT", "GATHER_SCATTER", "CYCLE"})


def iter_records(path: Path, *, as_of: datetime | None = None) -> Iterator[dict[str, Any]]:
    """Đọc từng dòng JSONL, lọc theo mốc thời gian nếu có.

    Đọc theo dòng chứ không nạp cả file: bản v1 nặng 635 MB.
    """
    wanted = as_of.date().isoformat() if as_of else None
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if wanted and str(record.get("as_of_ts", ""))[:10] != wanted:
                continue
            yield record


def _stage(session: Session, records: Iterator[dict[str, Any]], *, chunk: int = 5_000) -> int:
    """Đổ bản ghi thô vào bảng tạm để đối chiếu bằng SQL."""
    session.execute(text("DROP TABLE IF EXISTS stage_graph_evidence"))
    session.execute(
        text(
            """CREATE TEMP TABLE stage_graph_evidence (
                   evidence_id TEXT, account_key TEXT, as_of_time TIMESTAMPTZ,
                   pattern TEXT, detector_version TEXT,
                   cycle_length INT, duration_hours DOUBLE PRECISION,
                   accounts JSONB, hops JSONB
               )"""
        )
    )

    batch: list[dict[str, Any]] = []
    total = 0
    for record in records:
        accounts = record.get("accounts") or []
        hops = record.get("hops") or []
        if not hops or not accounts:
            continue
        batch.append(
            {
                "evidence_id": record["evidence_id"],
                # Tài khoản chủ thể là đích của cạnh cuối cùng — nơi dòng tiền
                # hội tụ. Đây là tài khoản mà cảnh báo nói tới.
                "account_key": hops[-1]["to_account_key"],
                "as_of_time": record["as_of_ts"],
                "pattern": record.get("detected_pattern") or "UNKNOWN",
                "detector_version": record.get("detector_version") or "graph_v1",
                "cycle_length": record.get("cycle_length"),
                "duration_hours": record.get("duration_hours"),
                "accounts": json.dumps(accounts),
                "hops": json.dumps(hops),
            }
        )
        if len(batch) >= chunk:
            total += _flush(session, batch)
            batch.clear()
    if batch:
        total += _flush(session, batch)
    return total


def _flush(session: Session, batch: list[dict[str, Any]]) -> int:
    session.execute(
        text(
            """INSERT INTO stage_graph_evidence (
                   evidence_id, account_key, as_of_time, pattern, detector_version,
                   cycle_length, duration_hours, accounts, hops
               ) VALUES (
                   :evidence_id, :account_key, :as_of_time, :pattern, :detector_version,
                   :cycle_length, :duration_hours, CAST(:accounts AS jsonb), CAST(:hops AS jsonb)
               )"""
        ),
        batch,
    )
    return len(batch)


#: Dịch mã giao dịch và đối chiếu hai đầu tài khoản của từng cạnh.
#:
#: ``resolved`` chỉ giữ cạnh mà giao dịch tồn tại VÀ hai đầu khớp. ``complete``
#: giữ bản ghi mà **mọi** cạnh đều qua được — số cạnh khớp bằng số cạnh gốc.
_RESOLVE_SQL = """
WITH edges AS (
    SELECT s.evidence_id,
           hop->>'from_account_key' AS from_key,
           hop->>'to_account_key'   AS to_key,
           hop->>'transaction_id'   AS source_txn,
           ordinality AS hop_index
      FROM stage_graph_evidence s,
           LATERAL jsonb_array_elements(s.hops) WITH ORDINALITY AS h(hop, ordinality)
),
resolved AS (
    SELECT e.evidence_id, e.hop_index, t.transaction_id
      FROM edges e
      JOIN transaction t ON t.source_transaction_id = e.source_txn
     WHERE t.from_account_key = e.from_key
       AND t.to_account_key = e.to_key
),
counts AS (
    SELECT s.evidence_id,
           jsonb_array_length(s.hops) AS expected,
           count(r.transaction_id) AS matched
      FROM stage_graph_evidence s
      LEFT JOIN resolved r ON r.evidence_id = s.evidence_id
     GROUP BY s.evidence_id, s.hops
),
complete AS (
    SELECT evidence_id FROM counts WHERE matched = expected AND expected > 0
),
rebuilt AS (
    SELECT e.evidence_id,
           jsonb_agg(
               jsonb_build_object(
                   'from', e.from_key,
                   'to', e.to_key,
                   'transaction_id', r.transaction_id::text
               ) ORDER BY e.hop_index
           ) AS edges
      FROM edges e
      JOIN resolved r ON r.evidence_id = e.evidence_id AND r.hop_index = e.hop_index
     WHERE e.evidence_id IN (SELECT evidence_id FROM complete)
     GROUP BY e.evidence_id
)
INSERT INTO graph_detector_evidence (
    evidence_id, account_key, as_of_time, pattern, detector_version, payload
)
SELECT s.evidence_id, s.account_key, s.as_of_time, s.pattern, s.detector_version,
       -- KHÔNG lưu 'available' vào payload: đó là trường suy ra lúc đọc, không
       -- phải dữ liệu. Lưu nó vào đây khiến GetGraphEvidence nhận hai lần cùng
       -- một tham số và ném TypeError.
       jsonb_strip_nulls(jsonb_build_object(
           'pattern', s.pattern,
           'accounts', s.accounts,
           'edges', b.edges,
           'cycle_length', s.cycle_length,
           'duration_hours', s.duration_hours
       ))
  FROM stage_graph_evidence s
  JOIN rebuilt b ON b.evidence_id = s.evidence_id
ON CONFLICT (evidence_id) DO NOTHING
"""


def load(
    session: Session,
    *,
    path: Path = DEFAULT_EVIDENCE,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Nạp bằng chứng đồ thị đã đối chiếu vào ``graph_detector_evidence``."""
    if not path.is_file():
        raise FileNotFoundError(path)

    staged = _stage(session, iter_records(path, as_of=as_of))
    if staged == 0:
        return {"staged": 0, "loaded": 0, "dropped": 0, "by_pattern": {}}

    result = session.execute(text(_RESOLVE_SQL))
    loaded = result.rowcount if result.rowcount is not None else 0

    by_pattern = {
        row["pattern"]: int(row["n"])
        for row in session.execute(
            text(
                """SELECT pattern, count(*) AS n FROM graph_detector_evidence
                    GROUP BY pattern ORDER BY pattern"""
            )
        ).mappings()
    }
    session.execute(text("DROP TABLE IF EXISTS stage_graph_evidence"))

    dropped = staged - loaded
    if dropped:
        logger.warning(
            "Loại %d/%d bản ghi bằng chứng vì có cạnh không khớp bảng transaction. "
            "Thường là do bằng chứng được tính trên một ảnh chụp dữ liệu khác.",
            dropped,
            staged,
        )
    return {"staged": staged, "loaded": loaded, "dropped": dropped, "by_pattern": by_pattern}
