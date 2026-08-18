/** Nhãn tiếng Việt cho đặc trưng hành vi và đặc trưng đồ thị.
 *
 * Khối bằng chứng trước đây đổ thẳng JSON ra màn hình, nên chuyên viên phải đọc
 * `median_dwell_time: 999.0` rồi tự đoán đơn vị và ý nghĩa. Bảng này biến mỗi
 * khoá thành một câu đọc được, kèm đơn vị và cách định dạng.
 *
 * Khoá nào chưa có ở đây vẫn hiện ra — dưới dạng tên gốc — chứ không bị giấu đi.
 * Giấu một đặc trưng là giấu bằng chứng.
 */

export type FeatureFormat = "count" | "amount" | "ratio" | "hours" | "days" | "raw";

export interface FeatureMeta {
  label: string;
  format: FeatureFormat;
  /** Giải thích ngắn, hiện khi rê chuột. Chỉ viết khi tên chưa đủ rõ. */
  hint?: string;
}

export const FEATURE_META: Record<string, FeatureMeta> = {
  txn_count: { label: "Số giao dịch", format: "count" },
  incoming_count: { label: "Giao dịch nhận", format: "count" },
  outgoing_count: { label: "Giao dịch gửi", format: "count" },
  active_days: { label: "Số ngày có phát sinh", format: "days" },
  txn_per_active_day: { label: "Giao dịch mỗi ngày hoạt động", format: "ratio" },

  total_inflow: { label: "Tổng tiền vào", format: "amount" },
  total_outflow: { label: "Tổng tiền ra", format: "amount" },
  net_flow: { label: "Chênh lệch vào − ra", format: "amount" },
  median_amount: { label: "Số tiền trung vị", format: "amount" },
  amount_std: { label: "Độ lệch chuẩn số tiền", format: "amount", hint: "Càng nhỏ nghĩa là các khoản càng giống nhau" },
  p90_amount: { label: "Số tiền ở phân vị 90", format: "amount" },

  outflow_inflow_ratio: { label: "Tỷ lệ tiền ra trên tiền vào", format: "ratio" },
  rapid_outflow_ratio: {
    label: "Tỷ lệ tiền ra trong 2 giờ sau khi nhận",
    format: "ratio",
    hint: "Cao nghĩa là tài khoản chỉ làm chỗ trung chuyển — tín hiệu của luật R02",
  },
  repeated_amount_ratio: {
    label: "Tỷ lệ số tiền lặp lại",
    format: "ratio",
    hint: "Cao nghĩa là nhiều giao dịch có cùng giá trị",
  },
  new_counterparty_ratio: { label: "Tỷ lệ đối tác mới", format: "ratio" },

  median_dwell_time: {
    label: "Thời gian tiền nằm lại (trung vị)",
    format: "hours",
    hint: "Khoảng cách từ lúc nhận tới lúc chuyển đi",
  },
  median_inter_txn_gap: { label: "Khoảng cách giữa hai giao dịch (trung vị)", format: "hours" },
  p10_inter_txn_gap: { label: "Khoảng cách giữa hai giao dịch (nhanh nhất 10%)", format: "hours" },

  unique_in_counterparties: { label: "Số đối tác gửi tiền đến", format: "count" },
  unique_out_counterparties: { label: "Số đối tác nhận tiền", format: "count" },
  unique_counterparties: { label: "Tổng số đối tác", format: "count" },

  fan_in: { label: "Số nguồn gửi vào", format: "count" },
  fan_out: { label: "Số đích nhận ra", format: "count" },
  cycle_length: { label: "Độ dài chu trình", format: "count", hint: "Số chặng để tiền quay về tài khoản ban đầu" },
  duration_hours: { label: "Thời gian hoàn tất", format: "hours" },
};

/** Nhóm để bảng dài không thành một danh sách phẳng khó đọc. */
export const FEATURE_GROUPS: { title: string; keys: string[] }[] = [
  { title: "Quy mô hoạt động", keys: ["txn_count", "incoming_count", "outgoing_count", "active_days", "txn_per_active_day"] },
  { title: "Dòng tiền", keys: ["total_inflow", "total_outflow", "net_flow", "median_amount", "p90_amount", "amount_std"] },
  {
    title: "Nhịp luân chuyển",
    keys: ["rapid_outflow_ratio", "median_dwell_time", "median_inter_txn_gap", "p10_inter_txn_gap", "outflow_inflow_ratio"],
  },
  {
    title: "Đối tác và khuôn mẫu",
    keys: ["unique_in_counterparties", "unique_out_counterparties", "unique_counterparties", "new_counterparty_ratio", "repeated_amount_ratio"],
  },
];

export function featureMeta(key: string): FeatureMeta {
  return FEATURE_META[key] ?? { label: key, format: "raw" };
}

export function formatFeature(value: unknown, format: FeatureFormat): string {
  if (value === null || value === undefined) return "—";
  if (typeof value !== "number") return String(value);

  switch (format) {
    case "count":
      return value.toLocaleString("vi-VN");
    case "days":
      return `${value.toLocaleString("vi-VN")} ngày`;
    case "amount":
      return value.toLocaleString("vi-VN", { maximumFractionDigits: 2 });
    case "ratio":
      return value <= 1 && value >= 0 ? `${(value * 100).toFixed(1)}%` : value.toFixed(2);
    case "hours":
      // 999 là giá trị canh biên của bộ trích đặc trưng cho "không quan sát
      // được", không phải 999 giờ thật. Hiện đúng như vậy thay vì để chuyên
      // viên đọc nhầm thành 41 ngày.
      if (value >= 999) return "không quan sát được";
      if (value < 1) return `${Math.round(value * 60)} phút`;
      if (value < 48) return `${value.toFixed(1)} giờ`;
      return `${(value / 24).toFixed(1)} ngày`;
    default:
      return String(value);
  }
}
