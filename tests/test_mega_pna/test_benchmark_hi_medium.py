"""Suite ``hi-medium`` — chỉ chạy HI-Medium, chấm bằng cổng phát hành.

Suite ``gate``/``medium`` có sẵn buộc phải qua HI-Small và LI-Small trước. Bản
phát hành lần này chỉ làm HI-Medium, nên cần một đường đi không đọc, không ghi và
không chấm hai bộ dữ liệu kia. Bộ test dưới đây khoá đúng tính chất ấy.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

benchmark = pytest.importorskip("scripts.benchmark_mega_pna")


def _seed_report(
    reports_dir: Path,
    seed: int,
    *,
    f1: float,
    precision: float = 0.78,
    recall: float = 0.79,
    pr_auc: float = 0.80,
    validation_f1: float | None = None,
    dataset: str = "Medium_HI",
) -> None:
    path = benchmark.seed_report_path(reports_dir, dataset, "paper", seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "seed": seed,
                "best_epoch": 57,
                "seconds": 1234.5,
                "config": {"epochs": 80, "batch_size": 8192},
                "validation_at_best": {"f1": validation_f1 if validation_f1 is not None else f1},
                "test_paper_protocol": {
                    "f1": f1,
                    "precision": precision,
                    "recall": recall,
                    "pr_auc": pr_auc,
                },
            }
        )
    )


PASSING = [0.781, 0.779, 0.783, 0.777, 0.780]
SEEDS = [42, 43, 44, 45, 46]


def _write_passing(reports_dir: Path) -> None:
    for seed, f1 in zip(SEEDS, PASSING, strict=True):
        _seed_report(reports_dir, seed, f1=f1)


# --------------------------------------------------------------------------
# Giao diện dòng lệnh
# --------------------------------------------------------------------------


def test_cli_accepts_hi_medium_suite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["benchmark_mega_pna.py", "--suite", "hi-medium"])
    assert benchmark.parse_args().suite == "hi-medium"


def test_cli_still_accepts_existing_suites(monkeypatch: pytest.MonkeyPatch) -> None:
    """Suite mới là thêm vào, không được làm hỏng đường đi cũ."""
    for suite in ("gate", "medium", "all", "summarize"):
        monkeypatch.setattr(sys, "argv", ["benchmark_mega_pna.py", "--suite", suite])
        assert benchmark.parse_args().suite == suite


def test_cli_rejects_unknown_suite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["benchmark_mega_pna.py", "--suite", "hi_medium"])
    with pytest.raises(SystemExit):
        benchmark.parse_args()


def test_legacy_suites_still_require_five_seeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cổng tái lập chấm bằng dung sai công bố, chỉ có nghĩa khi đủ 5 seed."""
    monkeypatch.setattr(sys, "argv", ["benchmark_mega_pna.py", "--suite", "gate", "--seeds", "42", "43"])
    with pytest.raises(ValueError, match="exactly five seeds"):
        benchmark.main()


def test_empty_seed_list_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["benchmark_mega_pna.py", "--suite", "hi-medium", "--seeds"])
    with pytest.raises(SystemExit):
        benchmark.parse_args()


# --------------------------------------------------------------------------
# Chạy ít hơn 5 seed: cho phép, nhưng phải nói rõ mất gì
# --------------------------------------------------------------------------


def test_single_seed_run_is_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_report(tmp_path, 42, f1=0.78)
    monkeypatch.setattr(benchmark, "run_seed", lambda *a, **k: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark_mega_pna.py", "--suite", "hi-medium", "--seeds", "42", "--reports-dir", str(tmp_path)],
    )
    assert benchmark.main() == 0


def test_single_seed_is_flagged_not_comparable(tmp_path: Path) -> None:
    """Bảo vệ quan trọng nhất của chế độ một seed: không ai trích nhầm."""
    _seed_report(tmp_path, 42, f1=0.78)
    result = benchmark.summarize_hi_medium(tmp_path, [42])

    assert result["comparable_to_published"] is False
    assert "MỘT LẦN HUẤN LUYỆN" in result["comparability_note"]
    assert result["completed_seed_count"] == 1


def test_five_seeds_are_flagged_comparable(tmp_path: Path) -> None:
    _write_passing(tmp_path)
    assert benchmark.summarize_hi_medium(tmp_path, SEEDS)["comparable_to_published"] is True


def test_std_check_is_not_applicable_with_one_seed(tmp_path: Path) -> None:
    """Không đánh giá được thì để None — không phải False, cũng không âm thầm cho qua."""
    _seed_report(tmp_path, 42, f1=0.78)
    result = benchmark.summarize_hi_medium(tmp_path, [42])

    assert result["release_gate_checks"]["f1_std"] is None
    assert result["checks_not_applicable"] == ["f1_std"]
    assert result["aggregate"]["f1"]["std"] is None
    # Những phép kiểm còn lại vẫn phải chấm thật.
    assert result["release_gate_checks"]["f1_mean"] is True
    assert result["release_gate_passed"] is True


def test_single_seed_below_threshold_still_fails(tmp_path: Path) -> None:
    """Bỏ qua phép kiểm độ lệch không được nới lỏng những phép kiểm khác."""
    _seed_report(tmp_path, 42, f1=0.60)
    result = benchmark.summarize_hi_medium(tmp_path, [42])
    assert result["release_gate_checks"]["f1_mean"] is False
    assert result["release_gate_passed"] is False


# --------------------------------------------------------------------------
# Chỉ một bộ dữ liệu
# --------------------------------------------------------------------------


def test_runs_only_medium_hi(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Không được chạm Small_HI hay Small_LI, kể cả để đọc."""
    seen: list[tuple[str, str, int]] = []

    def fake_run_seed(args, dataset, arm, seed):  # noqa: ANN001, ANN202
        seen.append((dataset, arm, seed))
        _seed_report(args.reports_dir, seed, f1=PASSING[SEEDS.index(seed)])

    monkeypatch.setattr(benchmark, "run_seed", fake_run_seed)
    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark_mega_pna.py", "--suite", "hi-medium", "--reports-dir", str(tmp_path)],
    )
    assert benchmark.main() == 0
    assert {dataset for dataset, _, _ in seen} == {"Medium_HI"}
    assert [seed for _, _, seed in seen] == SEEDS


def test_writes_no_small_dataset_rows(tmp_path: Path) -> None:
    _write_passing(tmp_path)
    result = benchmark.write_hi_medium_summary(tmp_path, SEEDS)

    payload = json.dumps(result)
    assert "Small_HI" not in payload
    assert "Small_LI" not in payload
    assert result["dataset"] == "Medium_HI"
    # Khoá cũ của suite gate không được xuất hiện — nó sẽ khiến người đọc tưởng
    # cổng nhỏ đã chạy.
    assert "small_reproduction_gate_passed" not in result

    on_disk = json.loads((tmp_path / "benchmark.json").read_text())
    assert on_disk["dataset"] == "Medium_HI"


def test_ignores_small_dataset_reports_left_on_disk(tmp_path: Path) -> None:
    """Báo cáo cũ của bộ khác nằm cùng thư mục cũng không được lọt vào."""
    _write_passing(tmp_path)
    _seed_report(tmp_path, 42, f1=0.44, dataset="Small_LI")

    result = benchmark.summarize_hi_medium(tmp_path, SEEDS)
    assert result["completed_seed_count"] == 5
    assert all(row["f1"] > 0.7 for row in result["runs"])


# --------------------------------------------------------------------------
# Tổng hợp số liệu
# --------------------------------------------------------------------------


def test_aggregates_four_metrics(tmp_path: Path) -> None:
    _write_passing(tmp_path)
    result = benchmark.summarize_hi_medium(tmp_path, SEEDS)

    assert set(result["aggregate"]) == {"f1", "precision", "recall", "pr_auc"}
    f1 = result["aggregate"]["f1"]
    assert f1["mean"] == pytest.approx(sum(PASSING) / len(PASSING))
    assert f1["min"] == pytest.approx(min(PASSING))
    assert f1["max"] == pytest.approx(max(PASSING))
    assert f1["std"] is not None


def test_records_lowest_f1_and_completed_count(tmp_path: Path) -> None:
    _write_passing(tmp_path)
    result = benchmark.summarize_hi_medium(tmp_path, SEEDS)

    assert result["aggregate"]["f1"]["min"] == pytest.approx(0.777)
    assert result["completed_seed_count"] == 5
    assert result["missing_seeds"] == []


# --------------------------------------------------------------------------
# Chọn seed bằng validation, không bằng test
# --------------------------------------------------------------------------


def test_selects_seed_by_validation_not_test(tmp_path: Path) -> None:
    # Seed 44 có test F1 cao nhất nhưng validation thấp; seed 43 thắng.
    _seed_report(tmp_path, 42, f1=0.780, validation_f1=0.770)
    _seed_report(tmp_path, 43, f1=0.776, validation_f1=0.790)
    _seed_report(tmp_path, 44, f1=0.799, validation_f1=0.760)
    _seed_report(tmp_path, 45, f1=0.778, validation_f1=0.780)
    _seed_report(tmp_path, 46, f1=0.777, validation_f1=0.775)

    result = benchmark.summarize_hi_medium(tmp_path, SEEDS)
    assert result["selected_seed"] == 43


def test_selection_ties_break_to_smaller_seed(tmp_path: Path) -> None:
    for seed in SEEDS:
        _seed_report(tmp_path, seed, f1=0.78, validation_f1=0.78)
    assert benchmark.summarize_hi_medium(tmp_path, SEEDS)["selected_seed"] == 42


# --------------------------------------------------------------------------
# Cổng phát hành
# --------------------------------------------------------------------------


def test_gate_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_passing(tmp_path)
    monkeypatch.setattr(benchmark, "run_seed", lambda *a, **k: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark_mega_pna.py", "--suite", "hi-medium", "--reports-dir", str(tmp_path)],
    )
    assert benchmark.main() == 0
    assert benchmark.summarize_hi_medium(tmp_path, SEEDS)["release_gate_passed"] is True


@pytest.mark.parametrize(
    ("values", "failing_check"),
    [
        # Trung bình dưới 0,75
        ([0.74, 0.74, 0.74, 0.74, 0.74], "f1_mean"),
        # Trung bình đạt nhưng một seed tụt dưới 0,73 — đúng trường hợp mà chỉ
        # nhìn trung bình sẽ bỏ sót.
        ([0.80, 0.80, 0.80, 0.80, 0.72], "f1_min"),
        # Trung bình đạt, thấp nhất đạt, nhưng dao động quá 0,01.
        ([0.79, 0.76, 0.79, 0.76, 0.79], "f1_std"),
    ],
)
def test_gate_fails_on_f1(tmp_path: Path, values: list[float], failing_check: str) -> None:
    for seed, f1 in zip(SEEDS, values, strict=True):
        _seed_report(tmp_path, seed, f1=f1)
    result = benchmark.summarize_hi_medium(tmp_path, SEEDS)
    assert result["release_gate_passed"] is False
    assert result["release_gate_checks"][failing_check] is False


def test_gate_fails_on_precision_and_recall(tmp_path: Path) -> None:
    for seed in SEEDS:
        _seed_report(tmp_path, seed, f1=0.78, precision=0.65, recall=0.60)
    checks = benchmark.summarize_hi_medium(tmp_path, SEEDS)["release_gate_checks"]
    assert checks["precision_mean"] is False
    assert checks["recall_mean"] is False


def test_missing_seed_fails_and_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for seed, f1 in zip(SEEDS[:4], PASSING[:4], strict=True):
        _seed_report(tmp_path, seed, f1=f1)

    result = benchmark.summarize_hi_medium(tmp_path, SEEDS)
    assert result["completed_seed_count"] == 4
    assert result["missing_seeds"] == [46]
    assert result["comparable_to_published"] is False
    assert result["release_gate_passed"] is False

    monkeypatch.setattr(benchmark, "run_seed", lambda *a, **k: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark_mega_pna.py", "--suite", "hi-medium", "--reports-dir", str(tmp_path)],
    )
    assert benchmark.main() == 2


def test_failing_gate_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for seed in SEEDS:
        _seed_report(tmp_path, seed, f1=0.60)
    monkeypatch.setattr(benchmark, "run_seed", lambda *a, **k: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark_mega_pna.py", "--suite", "hi-medium", "--reports-dir", str(tmp_path)],
    )
    assert benchmark.main() == 3


# --------------------------------------------------------------------------
# Dùng lại seed đã chạy xong
# --------------------------------------------------------------------------


def test_reuses_completed_seed_with_matching_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_report(tmp_path, 42, f1=0.78)
    called: list[list[str]] = []
    monkeypatch.setattr(benchmark.subprocess, "run", lambda cmd, **k: called.append(cmd))

    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark_mega_pna.py", "--suite", "hi-medium", "--reports-dir", str(tmp_path)],
    )
    args = benchmark.parse_args()
    benchmark.run_seed(args, "Medium_HI", "paper", 42)

    assert called == []
    assert "Reuse" in capsys.readouterr().out


def test_rejects_reuse_when_config_differs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_report(tmp_path, 42, f1=0.78)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "benchmark_mega_pna.py",
            "--suite",
            "hi-medium",
            "--reports-dir",
            str(tmp_path),
            "--epochs",
            "40",
        ],
    )
    args = benchmark.parse_args()
    with pytest.raises(RuntimeError, match="different epoch/batch config"):
        benchmark.run_seed(args, "Medium_HI", "paper", 42)


def test_subprocess_forces_gnu_threading_layer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Không có biến này thì tiến trình con chết ngay ở dòng import.

    Tiến trình cha nạp numpy nên MKL chốt lớp luồng INTEL; tiến trình con nạp torch
    kéo theo libgomp, và hai thứ ấy xung khắc. Lỗi chỉ lộ ra khi chạy qua suite,
    không lộ khi gọi thẳng train_mega_pna.py.
    """
    captured: dict[str, object] = {}
    monkeypatch.setattr(benchmark.subprocess, "run", lambda cmd, **kw: captured.update(cmd=cmd, **kw))
    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark_mega_pna.py", "--suite", "hi-medium", "--seeds", "42", "--reports-dir", str(tmp_path)],
    )
    benchmark.run_seed(benchmark.parse_args(), "Medium_HI", "paper", 42)
    assert captured["env"]["MKL_THREADING_LAYER"] == "GNU"
