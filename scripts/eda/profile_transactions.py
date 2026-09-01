"""EDA file giao dịch của bộ IBM AML — một lượt streaming, không nạp cả file.

File `*_Trans.csv` có 11 cột và **hai cột đều tên `Account`**:

    Timestamp,From Bank,Account,To Bank,Account,Amount Received,
    Receiving Currency,Amount Paid,Payment Currency,Payment Format,Is Laundering

`pandas` sẽ đổi tên cột thứ hai thành `Account.1`, `csv.DictReader` thì giữ
một cột và âm thầm vứt cột kia. Cả hai đều là hành vi của thư viện, đổi giữa
các phiên bản, và không phải chỗ dựa được cho một luồng dữ liệu. Ở đây các
cột đọc **theo vị trí**.

## Mười phép đo và lý do từng phép

| # | Đo cái gì | Quyết định điều gì |
|---|---|---|
| 1 | Số dòng, số tài khoản, khoảng thời gian | Kiểm tra tải đúng file; cửa sổ quyết định độ dài cửa sổ đặc trưng |
| 2 | Tỉ lệ nhãn dương mức GIAO DỊCH | Tỉ lệ nền để báo cáo và để chọn chỉ số |
| 3 | Tỉ lệ nhãn dương mức TÀI KHOẢN | Tỉ lệ nền thật sự dùng cho precision@k, vì hàng đợi hiển thị theo tài khoản |
| 4 | Phân bố bậc vào / bậc ra | Ngưỡng loại hub; bao nhiêu tài khoản đủ lịch sử để tự so sánh |
| 5 | Phân bố nhãn dương THEO NGÀY | Quyết định chia tập theo thời gian có dùng được không |
| 6 | Kênh thanh toán × nhãn (lift) | Kênh nào là chữ ký bộ sinh và phải loại khỏi đặc trưng |
| 7 | Tiền tệ × nhãn (lift) | Đặc trưng số loại tiền tệ có mang chữ ký nhãn không |
| 8 | Phân bố giờ trong ngày | Đặc trưng theo giờ là tín hiệu hay là nhiễu |
| 9 | Số tiền, có điều kiện theo tiền tệ | Cách chuẩn hoá; ngưỡng T01 đặt ở đâu |
| 10 | Cạnh tự trỏ, lệch zero-padding ngân hàng | Hai lỗi im lặng làm hỏng đồ thị |

Phép đo số 5 là phép quan trọng nhất và dễ bị bỏ qua nhất: nếu nhãn dương
không phân bố đều theo thời gian thì cách chia theo thời gian sẽ để lại một
tập test gần như không có mẫu dương, và mọi chỉ số trên đó vô nghĩa.

Chạy:
    python scripts/eda/profile_transactions.py \
        --input data/raw/ibm-aml/LI-Small_Trans.csv \
        --output artifacts/eda/li_small_transactions.json
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

# Vị trí cột là hợp đồng; tên cột chỉ để kiểm tra đúng file.
C_TIMESTAMP = 0
C_FROM_BANK = 1
C_FROM_ACCOUNT = 2
C_TO_BANK = 3
C_TO_ACCOUNT = 4
C_AMOUNT_RECEIVED = 5
C_CURRENCY_RECEIVED = 6
C_AMOUNT_PAID = 7
C_CURRENCY_PAID = 8
C_FORMAT = 9
C_LABEL = 10
COLUMN_COUNT = 11

EXPECTED_HEADER = (
    "Timestamp",
    "From Bank",
    "Account",
    "To Bank",
    "Account",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
)


def _col(index: int) -> str:
    return f"f{index}"


def _account_keys(table: pa.Table, bank_col: int, account_col: int) -> pa.Array:
    """Ghép `bank:account` sau khi bỏ số 0 đứng đầu của mã ngân hàng."""
    bank = pc.utf8_ltrim(table.column(_col(bank_col)), characters="0")
    bank = pc.if_else(pc.equal(pc.utf8_length(bank), 0), pa.scalar("0"), bank)
    return pc.binary_join_element_wise(bank, table.column(_col(account_col)), ":")


def _quantile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(p * len(ordered)))]


def profile(path: Path, batch_bytes: int = 1 << 26) -> dict[str, Any]:
    started = time.time()

    out_degree: Counter[str] = Counter()
    in_degree: Counter[str] = Counter()
    laundering_accounts: set[str] = set()

    total_rows = 0
    laundering_rows = 0
    self_loops = 0
    cross_currency_rows = 0

    format_total: Counter[str] = Counter()
    format_laundering: Counter[str] = Counter()
    currency_total: Counter[str] = Counter()
    currency_laundering: Counter[str] = Counter()
    hour_total: Counter[str] = Counter()
    day_total: Counter[str] = Counter()
    day_laundering: Counter[str] = Counter()

    bank_raw: set[str] = set()
    bank_normalized: set[str] = set()

    amounts_sample: list[float] = []
    laundering_amounts: list[float] = []
    amount_by_currency: dict[str, list[float]] = {}

    min_ts = None
    max_ts = None

    reader = pacsv.open_csv(
        path,
        read_options=pacsv.ReadOptions(autogenerate_column_names=True, block_size=batch_bytes),
        parse_options=pacsv.ParseOptions(newlines_in_values=False),
        convert_options=pacsv.ConvertOptions(
            strings_can_be_null=False,
            column_types={_col(i): pa.string() for i in range(COLUMN_COUNT)},
        ),
    )

    first_batch = True
    for batch in reader:
        table = pa.Table.from_batches([batch])

        if first_batch:
            header = [table.column(_col(i))[0].as_py() for i in range(COLUMN_COUNT)]
            if tuple(h.strip() for h in header) != EXPECTED_HEADER:
                raise SystemExit(
                    "Header không khớp định dạng IBM AML.\n"
                    f"  mong đợi: {', '.join(EXPECTED_HEADER)}\n"
                    f"  đọc được: {', '.join(header)}"
                )
            table = table.slice(1)
            first_batch = False

        rows = table.num_rows
        if rows == 0:
            continue
        total_rows += rows

        source = _account_keys(table, C_FROM_BANK, C_FROM_ACCOUNT)
        target = _account_keys(table, C_TO_BANK, C_TO_ACCOUNT)
        self_loops += pc.sum(pc.cast(pc.equal(source, target), pa.int64())).as_py() or 0

        for array, counter in ((source, out_degree), (target, in_degree)):
            for item in pc.value_counts(array):
                counter[item["values"].as_py()] += item["counts"].as_py()

        for raw in pc.unique(table.column(_col(C_FROM_BANK))).to_pylist():
            bank_raw.add(raw)
            bank_normalized.add(raw.lstrip("0") or "0")

        timestamps = table.column(_col(C_TIMESTAMP)).to_pylist()
        for ts in timestamps:
            day_total[ts[:10]] += 1
            hour_total[ts[11:13]] += 1
        batch_min, batch_max = min(timestamps), max(timestamps)
        min_ts = batch_min if min_ts is None or batch_min < min_ts else min_ts
        max_ts = batch_max if max_ts is None or batch_max > max_ts else max_ts

        formats = table.column(_col(C_FORMAT)).to_pylist()
        currencies = table.column(_col(C_CURRENCY_PAID)).to_pylist()
        received = table.column(_col(C_CURRENCY_RECEIVED)).to_pylist()
        paid_amounts = table.column(_col(C_AMOUNT_PAID)).to_pylist()
        labels = table.column(_col(C_LABEL)).to_pylist()

        format_total.update(formats)
        currency_total.update(currencies)

        source_list = source.to_pylist()
        target_list = target.to_pylist()

        for i, label in enumerate(labels):
            if currencies[i] != received[i]:
                cross_currency_rows += 1
            try:
                amount = float(paid_amounts[i])
            except (TypeError, ValueError):
                amount = None
            if amount is not None:
                amount_by_currency.setdefault(currencies[i], [])
                bucket = amount_by_currency[currencies[i]]
                if len(bucket) < 200_000:
                    bucket.append(amount)
                if len(amounts_sample) < 500_000:
                    amounts_sample.append(amount)
            if label == "1":
                laundering_rows += 1
                laundering_accounts.add(source_list[i])
                laundering_accounts.add(target_list[i])
                format_laundering[formats[i]] += 1
                currency_laundering[currencies[i]] += 1
                day_laundering[timestamps[i][:10]] += 1
                if amount is not None:
                    laundering_amounts.append(amount)

    elapsed = time.time() - started
    all_accounts = set(out_degree) | set(in_degree)
    degrees = [out_degree.get(a, 0) + in_degree.get(a, 0) for a in all_accounts]
    base_rate_txn = laundering_rows / total_rows if total_rows else 0.0
    base_rate_acct = len(laundering_accounts) / len(all_accounts) if all_accounts else 0.0

    def lift_table(total: Counter[str], positive: Counter[str]) -> list[dict[str, Any]]:
        rows_out = []
        for name, count in total.most_common():
            pos = positive.get(name, 0)
            rate = pos / count if count else 0.0
            rows_out.append(
                {
                    "gia_tri": name,
                    "so_dong": count,
                    "ti_le_toan_file_pct": round(100 * count / total_rows, 3),
                    "so_dong_laundering": pos,
                    "ti_le_trong_laundering_pct": round(100 * pos / laundering_rows, 3) if laundering_rows else 0.0,
                    "P_laundering_pct": round(100 * rate, 4),
                    "lift": round(rate / base_rate_txn, 2) if base_rate_txn else None,
                }
            )
        return rows_out

    hours = sorted(hour_total.items())
    hour_share = [{"gio": h, "ti_le_pct": round(100 * c / total_rows, 3)} for h, c in hours]

    return {
        "nguon": {"file": path.name, "kich_thuoc_byte": path.stat().st_size},
        "thoi_gian_chay_giay": round(elapsed, 1),
        # 1 — quy mô và khoảng thời gian
        "quy_mo": {
            "so_giao_dich": total_rows,
            "so_tai_khoan": len(all_accounts),
            "moc_dau": min_ts,
            "moc_cuoi": max_ts,
            "so_ngay_co_giao_dich": len(day_total),
        },
        # 2 và 3 — hai tỉ lệ nền
        "ti_le_nen": {
            "dong_laundering": laundering_rows,
            "muc_giao_dich_pct": round(100 * base_rate_txn, 4),
            "tai_khoan_cham_laundering": len(laundering_accounts),
            "muc_tai_khoan_pct": round(100 * base_rate_acct, 4),
            "ti_so_giua_hai_muc": round(base_rate_acct / base_rate_txn, 1) if base_rate_txn else None,
        },
        # 4 — bậc
        "bac": {
            "tong": {f"p{int(p * 100)}": _quantile(degrees, p) for p in (0.25, 0.5, 0.75, 0.95, 0.99)}
            | {"max": max(degrees) if degrees else 0},
            "so_tai_khoan_bac_>=20": sum(1 for d in degrees if d >= 20),
            "so_tai_khoan_bac_>=100": sum(1 for d in degrees if d >= 100),
            "so_tai_khoan_bac_>=1000": sum(1 for d in degrees if d >= 1000),
            "bac_ra_max": max(out_degree.values()) if out_degree else 0,
            "bac_vao_max": max(in_degree.values()) if in_degree else 0,
        },
        # 5 — phân bố nhãn theo ngày  ← phép đo quan trọng nhất
        "nhan_theo_ngay": [
            {"ngay": d, "tong_giao_dich": day_total[d], "laundering": day_laundering.get(d, 0)}
            for d in sorted(day_total)
        ],
        # 6 và 7 — lift theo kênh và tiền tệ
        "kenh_thanh_toan": lift_table(format_total, format_laundering),
        "tien_te": lift_table(currency_total, currency_laundering)[:10],
        # 8 — giờ trong ngày
        "gio_trong_ngay": {
            "phan_bo": hour_share,
            "ti_le_min_pct": min(x["ti_le_pct"] for x in hour_share) if hour_share else None,
            "ti_le_max_pct": max(x["ti_le_pct"] for x in hour_share) if hour_share else None,
            "ky_vong_neu_deu_pct": round(100 / max(len(hour_share), 1), 3),
        },
        # 9 — số tiền
        "so_tien": {
            "toan_bo_mau": {f"p{int(p * 100)}": _quantile(amounts_sample, p) for p in (0.25, 0.5, 0.75, 0.95)},
            "chi_dong_laundering": {
                f"p{int(p * 100)}": _quantile(laundering_amounts, p) for p in (0.25, 0.5, 0.75, 0.95)
            },
            "theo_tien_te": {
                cur: {f"p{int(p * 100)}": _quantile(vals, p) for p in (0.25, 0.5, 0.75)}
                for cur, vals in sorted(amount_by_currency.items(), key=lambda kv: -len(kv[1]))[:6]
            },
            "dong_cheo_tien_te": cross_currency_rows,
            "ti_le_cheo_tien_te_pct": round(100 * cross_currency_rows / total_rows, 3) if total_rows else 0,
        },
        # 10 — hai lỗi im lặng
        "loi_im_lang": {
            "canh_tu_tro": self_loops,
            "ti_le_canh_tu_tro_pct": round(100 * self_loops / total_rows, 2) if total_rows else 0,
            "ma_ngan_hang_tho": len(bank_raw),
            "ma_ngan_hang_sau_chuan_hoa": len(bank_normalized),
            "so_ma_bi_gop_do_zero_padding": len(bank_raw) - len(bank_normalized),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"Không thấy file: {args.input}")

    result = profile(args.input)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"Đã ghi {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
