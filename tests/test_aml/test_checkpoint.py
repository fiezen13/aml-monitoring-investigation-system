"""Điểm dừng và theo dõi xác nhận.

Câu hỏi mà file này trả lời: sau khi producer bị giết giữa chừng, lần chạy
tiếp theo bắt đầu từ đâu, và liệu có dòng nào lọt qua khe không.
"""

from pathlib import Path

from src.aml.checkpoint import AckTracker, Checkpoint, CheckpointStore
from src.aml.schema import utc_now_iso


def make_checkpoint(line: int, source_file: str = "HI-Small_Trans.csv") -> Checkpoint:
    return Checkpoint(
        source_file=source_file,
        last_acked_line=line,
        last_transaction_id="deadbeef" * 4,
        records_acked=line - 1,
        updated_at=utc_now_iso(),
    )


def test_round_trip(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "cp.json")
    store.save(make_checkpoint(1000))
    loaded = store.load()
    assert loaded is not None
    assert loaded.last_acked_line == 1000
    assert loaded.source_file == "HI-Small_Trans.csv"


def test_resume_continues_after_last_acked_line(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "cp.json")
    store.save(make_checkpoint(1000))
    assert store.resume_line("HI-Small_Trans.csv") == 1001


def test_checkpoint_of_another_file_is_ignored(tmp_path: Path) -> None:
    """Đổi bộ dữ liệu mà vẫn tiếp tục từ số dòng cũ sẽ bỏ qua phần đầu file mới."""
    store = CheckpointStore(tmp_path / "cp.json")
    store.save(make_checkpoint(1000, source_file="HI-Small_Trans.csv"))
    assert store.resume_line("LI-Large_Trans.csv") == 0


def test_corrupt_checkpoint_falls_back_to_beginning(tmp_path: Path) -> None:
    path = tmp_path / "cp.json"
    path.write_text("{ này không phải JSON", encoding="utf-8")
    assert CheckpointStore(path).resume_line("HI-Small_Trans.csv") == 0


def test_disabled_store_writes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "cp.json"
    store = CheckpointStore(path, enabled=False)
    store.save(make_checkpoint(10))
    assert not path.exists()


def test_save_leaves_no_temporary_files(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "cp.json")
    store.save(make_checkpoint(1))
    store.save(make_checkpoint(2))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cp.json"]


# ---- AckTracker --------------------------------------------------------


def test_safe_line_never_passes_an_unacked_line() -> None:
    """Kafka xác nhận không theo thứ tự; điểm dừng thì phải theo thứ tự.

    Dòng 12 xong trước dòng 11. Chốt ở 12 sẽ đánh mất dòng 11 khi chạy lại,
    nên mốc an toàn phải dừng ở 10.
    """
    tracker = AckTracker()
    for line in (10, 11, 12):
        tracker.on_produced(line)
    tracker.on_acked(10, "a")
    tracker.on_acked(12, "c")
    assert tracker.safe_line == 10

    tracker.on_acked(11, "b")
    assert tracker.safe_line == 12


def test_failed_message_holds_the_checkpoint_back() -> None:
    tracker = AckTracker()
    tracker.on_produced(5)
    tracker.on_produced(6)
    tracker.on_acked(6, "b")
    tracker.on_failed(5)
    assert tracker.safe_line == 4


def test_safe_line_is_zero_before_anything_is_produced() -> None:
    assert AckTracker().safe_line == 0


def test_in_flight_drains_to_zero() -> None:
    tracker = AckTracker()
    tracker.on_produced(2)
    assert tracker.in_flight == 1
    tracker.on_acked(2, "x")
    assert tracker.in_flight == 0
    assert tracker.acked == 1
    assert tracker.last_transaction_id == "x"
