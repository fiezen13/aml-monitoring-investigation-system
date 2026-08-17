"""Dừng sớm theo validation.

Vòng huấn luyện **vốn đã** giữ checkpoint theo validation F1 tốt nhất, nên những
epoch sau đỉnh không đổi kết quả — chúng chỉ tốn tiền máy. Trên HI-Medium một
epoch mất 44 phút, nên 80 epoch × 5 seed là 293 giờ GPU.

Bộ test này khoá hai điều: dừng đúng lúc, và **dừng không làm đổi kết quả**.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.mega_pna.config import MegaPnaConfig  # noqa: E402


def simulate(curve: list[float], *, patience: int, epochs: int | None = None) -> dict[str, object]:
    """Chạy đúng logic dừng sớm của ``train_one_seed`` trên một đường cong cho sẵn.

    Không dựng mô hình thật: phần cần kiểm là **quy tắc dừng**, và tách nó ra khỏi
    PyTorch cho phép kiểm hàng chục kịch bản trong vài mili giây thay vì vài giờ GPU.
    Logic dưới đây phải khớp từng dòng với vòng lặp trong ``training.py``.
    """
    total = epochs if epochs is not None else len(curve)
    best_f1 = -1.0
    best_epoch = 0
    without = 0
    stopped_early = False
    ran = 0

    for epoch in range(1, total + 1):
        if epoch > len(curve):
            break
        validation_f1 = curve[epoch - 1]
        ran = epoch
        if validation_f1 > best_f1:
            without = 0
            best_f1 = validation_f1
            best_epoch = epoch
        else:
            without += 1
            if patience and without >= patience:
                stopped_early = True
                break

    return {
        "best_epoch": best_epoch,
        "best_f1": best_f1,
        "epochs_run": ran,
        "stopped_early": stopped_early,
    }


# --------------------------------------------------------------------------
# Cấu hình
# --------------------------------------------------------------------------


def test_patience_defaults_to_disabled() -> None:
    """Mặc định phải giữ nguyên hành vi cũ — không ai bị dừng sớm ngoài ý muốn."""
    assert MegaPnaConfig().patience == 0


def test_patience_is_recorded_in_config_dict() -> None:
    """Báo cáo phải nói rõ đã chạy với patience nào, nếu không thì không tái lập được."""
    assert MegaPnaConfig(patience=10).to_dict()["patience"] == 10


def test_patience_does_not_break_validate() -> None:
    MegaPnaConfig(patience=10).validate()


# --------------------------------------------------------------------------
# Quy tắc dừng
# --------------------------------------------------------------------------


def test_disabled_patience_runs_every_epoch() -> None:
    curve = [0.61, 0.60, 0.60, 0.60, 0.60, 0.60]
    result = simulate(curve, patience=0)
    assert result["epochs_run"] == 6
    assert result["stopped_early"] is False


def test_stops_after_patience_epochs_without_improvement() -> None:
    # Đỉnh ở epoch 2, rồi ba epoch không cải thiện.
    curve = [0.60, 0.65, 0.64, 0.63, 0.64, 0.62, 0.61]
    result = simulate(curve, patience=3)
    assert result["best_epoch"] == 2
    assert result["epochs_run"] == 5
    assert result["stopped_early"] is True


def test_improvement_resets_the_counter() -> None:
    """Đi ngang rồi lên lại thì không được dừng — đây là kịch bản 'vai trước khi bật'."""
    curve = [0.60, 0.59, 0.59, 0.70, 0.69, 0.69, 0.69]
    result = simulate(curve, patience=3)
    assert result["best_epoch"] == 4
    assert result["best_f1"] == pytest.approx(0.70)
    assert result["epochs_run"] == 7
    assert result["stopped_early"] is True


def test_monotonic_curve_never_stops_early() -> None:
    curve = [0.50 + 0.01 * i for i in range(20)]
    result = simulate(curve, patience=5)
    assert result["stopped_early"] is False
    assert result["epochs_run"] == 20
    assert result["best_epoch"] == 20


def test_flat_curve_from_the_start_stops_promptly() -> None:
    curve = [0.61] + [0.61] * 20
    result = simulate(curve, patience=5)
    assert result["best_epoch"] == 1
    assert result["epochs_run"] == 6
    assert result["stopped_early"] is True


# --------------------------------------------------------------------------
# Tính chất quan trọng nhất: dừng sớm KHÔNG đổi kết quả
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "curve",
    [
        [0.60, 0.65, 0.64, 0.63, 0.62, 0.61, 0.60, 0.59],
        [0.61, 0.61, 0.62, 0.60, 0.60, 0.60, 0.59, 0.58],
        [0.30, 0.45, 0.55, 0.62, 0.61, 0.60, 0.60, 0.59],
    ],
)
def test_early_stop_selects_same_checkpoint_as_full_run(curve: list[float]) -> None:
    """Đây là lý do dừng sớm an toàn.

    Checkpoint được chọn theo **đỉnh validation**. Nếu đỉnh đã đi qua và không bao
    giờ bị vượt nữa, thì chạy tiếp hay dừng lại cũng chọn đúng một checkpoint ấy —
    chỉ khác số tiền máy đã trả.
    """
    full = simulate(curve, patience=0)
    early = simulate(curve, patience=3)

    assert early["best_epoch"] == full["best_epoch"]
    assert early["best_f1"] == pytest.approx(full["best_f1"])
    assert early["epochs_run"] <= full["epochs_run"]


def test_patience_too_short_can_miss_a_later_peak() -> None:
    """Giới hạn thật của dừng sớm, viết ra để người sau không tưởng nó miễn phí.

    Với patience quá ngắn, một đỉnh muộn sẽ bị bỏ lỡ. Đó là lý do chọn 10 chứ
    không phải 2 hay 3.
    """
    curve = [0.60, 0.59, 0.58, 0.57, 0.80]
    assert simulate(curve, patience=3)["best_f1"] == pytest.approx(0.60)
    assert simulate(curve, patience=10)["best_f1"] == pytest.approx(0.80)


def test_epoch_ceiling_still_applies() -> None:
    """patience không được phép kéo dài quá ``--epochs``."""
    curve = [0.50 + 0.01 * i for i in range(100)]
    result = simulate(curve, patience=10, epochs=30)
    assert result["epochs_run"] == 30
    assert result["stopped_early"] is False
