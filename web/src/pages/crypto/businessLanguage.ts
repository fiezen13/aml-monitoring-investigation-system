/**
 * Lớp dịch KỸ THUẬT → NGHIỆP VỤ cho chuyên viên AML (không cần biết ML).
 *
 * Nguồn sự thật: tên đặc trưng ĐÃ PHỤC HỒI (DFRWS 2026) nằm ở `driver.label`.
 * Ở đây CHỈ dịch sang khái niệm nghiệp vụ, KHÔNG suy diễn hành vi (rửa
 * tiền/structuring…), KHÔNG dùng SHAP/percentile/feature/model.
 *
 * RÀO CHẮN §4/§24 (đã sửa): SHAP dương KHÔNG có nghĩa "giá trị cao/bất thường".
 * Khi CHƯA có mốc so sánh (percentile/reference), TUYỆT ĐỐI không nói "bất
 * thường / khác đáng kể / cao hơn thông thường". Chỉ được nói yếu tố đó là "một
 * trong những điểm khiến hệ thống tăng mức ưu tiên rà soát".
 *
 * RÀO CHẮN §7/§8 (thêm mới): nhóm dựa trên GIAO DỊCH TRƯỚC (predecessor) chỉ hiện
 * khi có giao dịch thượng nguồn; nhóm dựa trên GIAO DỊCH SAU (successor) chỉ hiện
 * khi có giao dịch hạ nguồn — không thì mâu thuẫn với đồ thị ("0 giao dịch sau").
 */
import type { FcBitcoinDriver } from "../../api/client";

/** side: nhóm phụ thuộc chiều nào của đồ thị (để chặn khi count=0). */
type Side = "upstream_tx" | "downstream_tx" | "local";

interface Category {
  key: string;
  title: string;
  description: string;
  side: Side;
  /** Đánh dấu tín hiệu quan sát SAU giao dịch (temporal — không phải real-time). */
  afterTransaction?: boolean;
}

/** Ánh xạ tên đặc trưng phục hồi → nhóm nghiệp vụ. Thứ tự kiểm tra quan trọng. */
function categoryOf(name: string): Category | null {
  const n = name.toLowerCase();
  // Giao dịch trước/sau (predecessor/successor) — kiểm trước "addresses".
  if (n.includes("of input txs"))
    return { key: "PRED_TX", side: "upstream_tx", title: "Đặc điểm của các giao dịch nguồn", description: "Các giao dịch đưa tiền tới giao dịch này là một trong những nhóm yếu tố khiến hệ thống tăng mức ưu tiên rà soát." };
  if (n.includes("of output txs"))
    return { key: "SUCC_TX", side: "downstream_tx", afterTransaction: true, title: "Đặc điểm của các giao dịch tiếp theo", description: "Các giao dịch nhận tiền từ giao dịch này là một trong những nhóm yếu tố khiến hệ thống tăng mức ưu tiên rà soát." };
  if (n.includes("of input addresses"))
    return { key: "IN_ADDR", side: "local", title: "Hoạt động của các địa chỉ gửi tiền", description: "Lịch sử hoạt động của các địa chỉ đưa tiền vào giao dịch là một trong những yếu tố khiến hệ thống tăng mức ưu tiên rà soát." };
  if (n.includes("of output addresses"))
    return { key: "OUT_ADDR", side: "local", title: "Hoạt động của các địa chỉ nhận tiền", description: "Lịch sử hoạt động của các địa chỉ nhận tiền từ giao dịch là một trong những yếu tố khiến hệ thống tăng mức ưu tiên rà soát." };
  if (n.includes("output values") || (n.includes("output") && n.includes("value")))
    return { key: "OUT_VAL", side: "local", title: "Cách phân bổ giá trị ở các đầu nhận", description: "Cách chia giá trị giữa các đầu nhận của giao dịch là một trong những yếu tố khiến hệ thống tăng mức ưu tiên rà soát." };
  if (n.includes("input values") || (n.includes("input") && n.includes("value")))
    return { key: "IN_VAL", side: "local", title: "Cách hình thành nguồn tiền đầu vào", description: "Cách các nguồn tiền đầu vào hợp thành giao dịch là một trong những yếu tố khiến hệ thống tăng mức ưu tiên rà soát." };
  if (n.includes("output"))
    return { key: "OUT_STRUCT", side: "local", title: "Cấu trúc các địa chỉ nhận tiền", description: "Cấu trúc các đầu nhận của giao dịch là một trong những yếu tố khiến hệ thống tăng mức ưu tiên rà soát." };
  if (n.includes("input"))
    return { key: "IN_STRUCT", side: "local", title: "Cấu trúc các nguồn tiền vào", description: "Cấu trúc các nguồn tiền vào của giao dịch là một trong những yếu tố khiến hệ thống tăng mức ưu tiên rà soát." };
  if (n.includes("volume"))
    return { key: "VOLUME", side: "local", title: "Quy mô giá trị giao dịch", description: "Quy mô giá trị của giao dịch là một trong những yếu tố khiến hệ thống tăng mức ưu tiên rà soát." };
  if (n.includes("fee"))
    return { key: "FEES", side: "local", title: "Mức phí giao dịch", description: "Mức phí của giao dịch là một trong những yếu tố khiến hệ thống tăng mức ưu tiên rà soát." };
  return null; // time step / không xếp nhóm → bỏ khỏi lý do nghiệp vụ
}

export interface BusinessReason {
  title: string;
  description: string;
  impact: "CAO" | "TRUNG BÌNH" | "THẤP";
  afterTransaction?: boolean;
}

export interface GraphCounts {
  upstreamCount: number;
  downstreamCount: number;
}

/**
 * 2–4 dấu hiệu nghiệp vụ, gộp theo nhóm, xếp theo tổng độ ảnh hưởng. Chỉ dùng
 * đặc trưng ĐÃ PHỤC HỒI (không bịa); đặc trưng chưa giải nghĩa bị bỏ qua.
 *
 * `counts` để chặn nhóm giao dịch-trước/sau khi đồ thị không có chiều đó (§7).
 */
export function businessReasons(drivers: FcBitcoinDriver[], counts?: GraphCounts): BusinessReason[] {
  const agg = new Map<string, { cat: Category; weight: number }>();
  for (const d of drivers) {
    if (!d.meaningful || !d.label) continue;
    if (d.contribution <= 0) continue; // chỉ yếu tố LÀM TĂNG mức ưu tiên
    const cat = categoryOf(d.label);
    if (!cat) continue;
    // Chặn tín hiệu về giao dịch trước/sau khi đồ thị không có chiều tương ứng.
    if (counts) {
      if (cat.side === "upstream_tx" && counts.upstreamCount <= 0) continue;
      if (cat.side === "downstream_tx" && counts.downstreamCount <= 0) continue;
    }
    const cur = agg.get(cat.key);
    if (cur) cur.weight += Math.abs(d.contribution);
    else agg.set(cat.key, { cat, weight: Math.abs(d.contribution) });
  }
  const ranked = [...agg.values()].sort((a, b) => b.weight - a.weight).slice(0, 4);
  return ranked.map((r, i) => ({
    title: r.cat.title,
    description: r.cat.description,
    impact: i <= 1 ? "CAO" : i === 2 ? "TRUNG BÌNH" : "THẤP",
    afterTransaction: r.cat.afterTransaction,
  }));
}
