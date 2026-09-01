"""Phiên điều tra bị bỏ rơi phải được giao lại khi worker khởi động."""

from unittest.mock import patch

from src.worker.main import _mark_failed, requeue_orphans


def test_giao_lai_phien_mo_coi() -> None:
    """Việc bị mất khi worker tắt giữa chừng thì lần lên sau phải nhặt lại.

    Hàng đợi dùng ``blpop``: việc rời khỏi Redis *trước* khi chạy. Không có bước
    này thì bản ghi nằm ở QUEUED vĩnh viễn và giao diện treo ở "đang chờ".
    """
    with (
        patch("src.worker.main.get_session") as session_ctx,
        patch("src.worker.main.queue.enqueue") as enqueue,
    ):
        session = session_ctx.return_value.__enter__.return_value
        session.execute.return_value.scalars.return_value = ["INV-1", "INV-2"]

        assert requeue_orphans() == 2
        assert enqueue.call_count == 2
        assert enqueue.call_args_list[0].args[0] == "investigate_alert"
        assert enqueue.call_args_list[0].args[1] == {"investigation_id": "INV-1"}


def test_loi_co_so_du_lieu_khong_giet_worker() -> None:
    """Không nối được cơ sở dữ liệu lúc khởi động thì bỏ qua, không ném lỗi."""
    with (
        patch("src.worker.main.get_session", side_effect=RuntimeError("mất kết nối")),
        patch("src.worker.main.queue.enqueue") as enqueue,
    ):
        assert requeue_orphans() == 0
        enqueue.assert_not_called()


def test_ghi_that_bai_bang_phien_moi() -> None:
    """Lưới an toàn phải mở phiên mới, và chỉ ghi khi trạng thái chưa kết thúc.

    Dùng lại phiên cũ là vô nghĩa: nó thường đang hỏng, và đó chính là lý do
    đường ghi lỗi trước đó đã thất bại.
    """
    with patch("src.worker.main.get_session") as session_ctx:
        session = session_ctx.return_value.__enter__.return_value
        _mark_failed("INV-9", RuntimeError("mất kết nối"))

        session_ctx.assert_called_once()
        sql = str(session.execute.call_args.args[0])
        assert "status NOT IN" in sql
        assert session.execute.call_args.args[1]["reason"].startswith("RuntimeError: ")


def test_luoi_an_toan_khong_nem_tiep() -> None:
    """Cứu hộ mà ném lỗi thì che mất lỗi gốc — điều cần chẩn đoán."""
    with patch("src.worker.main.get_session", side_effect=RuntimeError("DB chết")):
        _mark_failed("INV-9", ValueError("lỗi gốc"))
