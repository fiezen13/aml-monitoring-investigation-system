"""Giải thích kết quả Bitcoin AML bằng ngôn ngữ đời thường cho chuyên viên.

Ràng buộc nền tảng: Elliptic++ ẩn danh phần lớn đặc trưng (``Local_feature_N``,
``Aggregate_feature_N``) — KHÔNG có ngữ nghĩa, nên không được bịa. Nhưng 17 đặc
trưng là **đọc được**: số địa chỉ gửi/nhận, tổng BTC, phí, kích thước… Bộ giải
thích chỉ nói về những đặc trưng đọc được ấy, bằng tiếng Việt thường, và luôn
đóng khung là NGHI VẤN thống kê — không kết luận, không gọi tên mẫu hình rửa
tiền (fan-in/peel-chain…) vì Elliptic++ không cung cấp nhãn ấy.

Tất định, không gọi mô hình ngôn ngữ: đặc trưng là số có ý nghĩa rõ, nên một
bản mô tả mạch lạc là đủ và không có chỗ để bịa.
"""

from __future__ import annotations

from src.bitcoin_aml.schemas import BitcoinExplanation, Prediction

#: Nhãn tiếng Việt cho các đặc trưng CÓ NGHĨA của Elliptic++. Chỉ những đặc trưng
#: này mới được nhắc trong câu giải thích; đặc trưng ẩn danh thì gộp chung là
#: "một số đặc trưng kỹ thuật khác", không bịa nghĩa.
MEANINGFUL_LABELS: dict[str, str] = {
    "in_txs_degree": "số giao dịch chuyển tiền vào",
    "out_txs_degree": "số giao dịch nhận tiền ra",
    "total_BTC": "tổng số Bitcoin của giao dịch",
    "fees": "phí giao dịch",
    "size": "kích thước giao dịch (byte)",
    "num_input_addresses": "số địa chỉ gửi tiền vào",
    "num_output_addresses": "số địa chỉ nhận tiền ra",
    "in_BTC_min": "khoản Bitcoin vào nhỏ nhất",
    "in_BTC_max": "khoản Bitcoin vào lớn nhất",
    "in_BTC_mean": "khoản Bitcoin vào trung bình",
    "in_BTC_median": "khoản Bitcoin vào trung vị",
    "in_BTC_total": "tổng Bitcoin vào",
    "out_BTC_min": "khoản Bitcoin ra nhỏ nhất",
    "out_BTC_max": "khoản Bitcoin ra lớn nhất",
    "out_BTC_mean": "khoản Bitcoin ra trung bình",
    "out_BTC_median": "khoản Bitcoin ra trung vị",
    "out_BTC_total": "tổng Bitcoin ra",
}

#: Ngưỡng "nhiều địa chỉ" để mô tả hình dạng — chỉ để chọn từ ngữ, không phải
#: nhãn ground-truth.
MANY_ADDRESSES = 5


def _num(value: float) -> str:
    """In số gọn: bỏ phần thập phân thừa cho số nguyên (số địa chỉ, byte…)."""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _shape_sentence(values: dict[str, float]) -> str | None:
    """Mô tả HÌNH DẠNG giao dịch từ số địa chỉ gửi/nhận, nếu có.

    Đây là quan sát trực tiếp từ số liệu, không phải kết luận. "Gom" hay "toả"
    chỉ là cách gọi hình dạng — nhiều người bình thường cũng có giao dịch như
    vậy, nên câu luôn kèm "cần rà soát", không phán là rửa tiền.
    """
    ins = values.get("num_input_addresses")
    outs = values.get("num_output_addresses")
    if ins is None or outs is None:
        return None
    ins_i, outs_i = int(round(ins)), int(round(outs))
    if ins_i >= MANY_ADDRESSES and outs_i <= 2:
        return (
            f"Giao dịch gom tiền từ {ins_i} địa chỉ khác nhau rồi dồn về {outs_i} địa chỉ — dáng gom tiền, nên soi kỹ."
        )
    if ins_i <= 2 and outs_i >= MANY_ADDRESSES:
        return (
            f"Giao dịch nhận tiền từ {ins_i} địa chỉ rồi chia ra {outs_i} địa chỉ — "
            "dáng chia nhỏ toả ra, kiểu khó lần theo."
        )
    return f"Giao dịch có {ins_i} địa chỉ gửi vào và {outs_i} địa chỉ nhận ra."


def build_explanation(
    feature_values: dict[str, float],
    importance: dict[str, float],
    prediction: Prediction,
) -> BitcoinExplanation:
    """Dựng câu giải thích đời thường từ kết quả RF và các đặc trưng đọc được.

    ``feature_values`` là {tên đặc trưng → giá trị của giao dịch này} cho đúng
    tập đặc trưng đã chọn. Chỉ những đặc trưng CÓ NGHĨA mới lên câu chữ.
    """
    score100 = round(prediction.risk_score * 100)
    if prediction.label == "illicit":
        headline = (
            f"Hệ thống nghi ngờ đây là giao dịch bất hợp pháp — mức nghi ngờ {score100}/100. "
            "Đây là nhận định thống kê, cần chuyên viên rà soát, chưa phải kết luận."
        )
    else:
        headline = f"Hệ thống đánh giá đây nhiều khả năng là giao dịch hợp pháp — mức nghi ngờ chỉ {score100}/100."

    reasons: list[str] = []
    shape = _shape_sentence(feature_values)
    if shape:
        reasons.append(shape)

    # Các đặc trưng CÓ NGHĨA nặng ký nhất mà mô hình dựa vào, kèm giá trị thật
    # của giao dịch — nói bằng tiếng thường, không nhắc tên cột kỹ thuật.
    meaningful_ranked = sorted(
        (name for name in feature_values if name in MEANINGFUL_LABELS),
        key=lambda name: importance.get(name, 0.0),
        reverse=True,
    )
    for name in meaningful_ranked[:3]:
        if name in ("num_input_addresses", "num_output_addresses"):
            continue  # đã nói ở câu hình dạng
        reasons.append(f"{MEANINGFUL_LABELS[name].capitalize()}: {_num(feature_values[name])}.")

    anonymous_count = sum(1 for name in feature_values if name not in MEANINGFUL_LABELS)
    caveat = (
        "Phần lớn căn cứ là các đặc trưng kỹ thuật ẩn danh của mạng Bitcoin "
        f"({anonymous_count} đặc trưng) mà mô hình học từ các giao dịch bất hợp pháp đã biết — "
        "không quy được về một hành vi cụ thể, và không có nhãn mẫu hình (trộn coin, chia chuỗi…) "
        "trong dữ liệu này. Hãy dùng kết quả như một tín hiệu ưu tiên rà soát."
    )
    return BitcoinExplanation(headline=headline, reasons=reasons, caveat=caveat)
