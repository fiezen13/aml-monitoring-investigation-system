from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MegaPnaConfig:
    """Paper-compatible hyperparameters for AML edge classification."""

    hidden_channels: int = 20
    num_layers: int = 2
    batch_size: int = 8192
    num_neighbors: tuple[int, int] = (100, 100)
    learning_rate: float = 0.0008
    dropout: float = 0.28
    class_weight_clean: float = 1.0
    class_weight_laundering: float = 7.0
    epochs: int = 80
    edge_updates: bool = True
    reverse_message_passing: bool = True
    ego_ids: bool = True
    flatten_parallel_edges: bool = True
    edge_aggregation: str = "pna"
    node_aggregation: str = "pna"

    #: Số tiến trình lấy mẫu láng giềng chạy song song.
    #:
    #: Đây **không** phải siêu tham số của mô hình — nó không đổi kiến trúc, không
    #: đổi cách học, chỉ đổi chỗ công việc lấy mẫu được làm.
    #:
    #: Vì sao cần: đo trên L40S với HI-Medium cho thấy GPU nhảy giữa 0% và 100%
    #: còn CPU chỉ dùng 2 trên 8 nhân. Bộ lấy mẫu chạy trong tiến trình chính nên
    #: GPU phải đứng chờ từng lô. Một epoch huấn luyện mất 46,5 phút, tức 80 epoch
    #: × 5 seed vượt xa dự trù.
    #:
    #: Để 0 là giữ hành vi cũ. Trên máy 8 nhân nên đặt 6: chừa 2 nhân cho tiến
    #: trình chính và cho việc chuyển dữ liệu sang GPU.
    #:
    #: Lưu ý khi báo cáo: đổi con số này làm đổi thứ tự tiêu thụ số ngẫu nhiên, nên
    #: kết quả không trùng khít với lần chạy ``num_workers=0``. Phải dùng **cùng
    #: một giá trị cho cả năm seed**, và giá trị ấy được ghi vào báo cáo.
    num_workers: int = 0

    #: Số epoch chịu đựng khi validation F1 không cải thiện, trước khi dừng.
    #:
    #: 0 là tắt — chạy đủ ``epochs``, giữ đúng hành vi cũ.
    #:
    #: Vì sao có: vòng huấn luyện **vốn đã** giữ checkpoint theo validation F1 tốt
    #: nhất, nên những epoch sau đỉnh không đổi kết quả — chúng chỉ tốn tiền máy.
    #: Trên HI-Medium một epoch mất 44 phút, nên 80 epoch × 5 seed là 293 giờ GPU.
    #: Dừng sớm để chính đường cong quyết định điểm dừng, thay vì đoán trước một
    #: con số epoch rồi trả tiền cho con số đoán ấy.
    #:
    #: Chỉ đọc validation, không bao giờ đọc test — nên không ảnh hưởng tính hợp lệ
    #: của số liệu báo cáo.
    patience: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def validate(self) -> None:
        if self.hidden_channels % 5:
            raise ValueError("hidden_channels must be divisible by the five PNA towers")
        if self.num_layers != len(self.num_neighbors):
            raise ValueError("num_neighbors must contain one value per GNN layer")
        if not all(self.num_neighbors):
            raise ValueError("neighbor sample sizes must be positive")
        if self.edge_aggregation != "pna" or self.node_aggregation != "pna":
            raise ValueError("This FIN-07 implementation intentionally supports MEGA-PNA only")
