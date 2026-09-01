"""Bộ nạp bằng chứng đồ thị — phần đọc file và lọc theo mốc thời gian.

Phần đối chiếu cạnh với bảng ``transaction`` chạy bằng SQL nên được kiểm ở
``tests/test_detection/test_graph_loader_integration.py``; ở đây chỉ kiểm phần
thuần Python, không cần cơ sở dữ liệu.
"""

import json
from datetime import UTC, datetime

import pytest

from src.detection.graph_loader import iter_records, load

RECORDS = [
    {
        "evidence_id": "EV_a",
        "as_of_ts": "2022-09-17T00:00:00+00:00",
        "detected_pattern": "CYCLE",
        "detector_version": "graph_cycle_v1",
        "cycle_length": 3,
        "duration_hours": 18.5,
        "accounts": ["001:A", "002:B", "003:C"],
        "hops": [
            {"from_account_key": "001:A", "to_account_key": "002:B", "transaction_id": "h1"},
            {"from_account_key": "002:B", "to_account_key": "003:C", "transaction_id": "h2"},
        ],
    },
    {
        "evidence_id": "EV_b",
        "as_of_ts": "2022-09-02T00:00:00+00:00",
        "detected_pattern": "FAN_IN",
        "detector_version": "graph_fan_v3_min",
        "cycle_length": None,
        "duration_hours": None,
        "accounts": ["004:D", "005:E"],
        "hops": [{"from_account_key": "004:D", "to_account_key": "005:E", "transaction_id": "h3"}],
    },
    {
        # Bản ghi rỗng: không có cạnh nào thì không chứng minh được gì.
        "evidence_id": "EV_c",
        "as_of_ts": "2022-09-17T00:00:00+00:00",
        "detected_pattern": "FAN_OUT",
        "detector_version": "graph_fan_v3_min",
        "accounts": [],
        "hops": [],
    },
]


@pytest.fixture
def evidence_file(tmp_path):
    path = tmp_path / "graph_evidence.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in RECORDS) + "\n", encoding="utf-8")
    return path


def test_reads_every_record_when_no_snapshot_is_given(evidence_file):
    assert [r["evidence_id"] for r in iter_records(evidence_file)] == ["EV_a", "EV_b", "EV_c"]


def test_filters_to_the_requested_snapshot(evidence_file):
    """Cảnh báo trỏ vào đúng một mốc; nạp cả lịch sử là lãng phí và gây nhiễu."""
    as_of = datetime(2022, 9, 17, tzinfo=UTC)
    got = [r["evidence_id"] for r in iter_records(evidence_file, as_of=as_of)]

    assert got == ["EV_a", "EV_c"]


def test_a_blank_line_does_not_break_the_stream(tmp_path):
    path = tmp_path / "with_blank.jsonl"
    path.write_text(json.dumps(RECORDS[0]) + "\n\n" + json.dumps(RECORDS[1]) + "\n", encoding="utf-8")

    assert len(list(iter_records(path))) == 2


def test_a_missing_file_fails_loudly(tmp_path):
    """Im lặng bỏ qua file thiếu sẽ tạo ra một nhánh graph rỗng mà không ai biết."""
    with pytest.raises(FileNotFoundError):
        load(None, path=tmp_path / "khong-ton-tai.jsonl")


# --- Phần cần cơ sở dữ liệu thật -------------------------------------------

pytestmark_integration = pytest.mark.integration


def _db_or_skip():
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError

    from src.db.session import get_engine

    engine = get_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        pytest.skip(f"PostgreSQL không sẵn sàng: {exc}")
    return engine


@pytest.mark.integration
def test_every_loaded_edge_matches_its_source_transaction():
    """Chốt chặn quan trọng nhất của cả nhánh đồ thị.

    Tác tử phản biện đối chiếu từng cạnh với bảng ``transaction``; một cạnh lệch
    là cả phiên điều tra bị đánh trượt. Truy vấn dưới đây đi ngược lại đúng phép
    kiểm đó trên toàn bộ dữ liệu đã nạp.
    """
    from sqlalchemy import text

    engine = _db_or_skip()
    with engine.connect() as connection:
        total = connection.execute(text("SELECT count(*) FROM graph_detector_evidence")).scalar_one()
        if not total:
            pytest.skip("Chưa nạp bằng chứng đồ thị")

        mismatched = connection.execute(
            text(
                """
                SELECT count(*)
                  FROM graph_detector_evidence g,
                       LATERAL jsonb_array_elements(g.payload->'edges') AS edge
                  LEFT JOIN transaction t
                         ON t.transaction_id = (edge->>'transaction_id')::bigint
                        AND t.from_account_key = edge->>'from'
                        AND t.to_account_key = edge->>'to'
                 WHERE t.transaction_id IS NULL
                """
            )
        ).scalar_one()

    assert mismatched == 0


@pytest.mark.integration
def test_loaded_payloads_satisfy_the_agent_facing_schema():
    """Payload phải dựng được thành GraphEvidenceResult, nếu không công cụ sẽ nổ."""
    from sqlalchemy import text

    from src.investigation.schemas import GraphEvidenceResult

    engine = _db_or_skip()
    with engine.connect() as connection:
        rows = (
            connection.execute(text("SELECT evidence_id, payload FROM graph_detector_evidence LIMIT 50"))
            .mappings()
            .all()
        )
    if not rows:
        pytest.skip("Chưa nạp bằng chứng đồ thị")

    for row in rows:
        # ``available`` do tầng công cụ quyết định, không nằm trong payload đã lưu.
        assert "available" not in row["payload"]
        result = GraphEvidenceResult(**row["payload"], evidence_id=row["evidence_id"], available=True)
        assert result.pattern
        assert result.edges
