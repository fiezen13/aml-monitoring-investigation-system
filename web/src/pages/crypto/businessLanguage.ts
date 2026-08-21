/**
 * Lớp dịch KỸ THUẬT → NGHIỆP VỤ cho chuyên viên AML (không cần biết ML).
 *
 * Nguồn sự thật: tên đặc trưng ĐÃ PHỤC HỒI (DFRWS 2026) nằm ở `driver.label`.
 * Ở đây CHỈ dịch sang khái niệm nghiệp vụ + câu chữ trung tính, KHÔNG suy diễn
 * hành vi (rửa tiền/structuring…), KHÔNG dùng SHAP/percentile/feature/model.
 *
 * §9: đóng góp SHAP dương KHÔNG có nghĩa "giá trị cao" — nên mô tả luôn TRUNG
 * TÍNH ("khác đáng kể so với giao dịch thông thường"), không gọi cao/thấp.
 */
import type { FcBitcoinDriver } from "../../api/client";

interface Category {
  key: string;
  title: string;
  description: string;
}

/** Ánh xạ tên đặc trưng phục hồi → nhóm nghiệp vụ. Thứ tự kiểm tra quan trọng. */
function categoryOf(name: string): Category | null {
  const n = name.toLowerCase();
  // Giao dịch trước/sau (predecessor/successor) — kiểm trước "addresses".
  if (n.includes("of input txs"))
    return { key: "PRED_TX", title: "Đặc điểm của các giao dịch trước đó", description: "Các giao dịch đưa tiền tới giao dịch này có đặc điểm khác đáng kể so với phần lớn giao dịch thông thường mà hệ thống đã phân tích." };
  if (n.includes("of output txs"))
    return { key: "SUCC_TX", title: "Đặc điểm của các giao dịch tiếp theo", description: "Các giao dịch nhận tiền từ giao dịch này có đặc điểm khác đáng kể so với phần lớn giao dịch thông thường." };
  if (n.includes("of input addresses"))
    return { key: "IN_ADDR", title: "Hoạt động của các địa chỉ gửi tiền", description: "Lịch sử giao dịch của các địa chỉ đưa tiền vào giao dịch này có đặc điểm khác đáng kể so với phần lớn giao dịch thông thường." };
  if (n.includes("of output addresses"))
    return { key: "OUT_ADDR", title: "Hoạt động của các địa chỉ nhận tiền", description: "Lịch sử giao dịch của các địa chỉ nhận tiền từ giao dịch này có đặc điểm khác đáng kể so với phần lớn giao dịch thông thường." };
  if (n.includes("output values") || (n.includes("output") && n.includes("value")))
    return { key: "OUT_VAL", title: "Cách phân bổ giá trị ở các đầu nhận", description: "Cách chia giá trị giữa các đầu nhận của giao dịch khác đáng kể so với nhiều giao dịch thông thường." };
  if (n.includes("input values") || (n.includes("input") && n.includes("value")))
    return { key: "IN_VAL", title: "Cách hình thành nguồn tiền đầu vào", description: "Cách các nguồn tiền đầu vào hợp thành giao dịch có đặc điểm khác đáng kể so với giao dịch thông thường." };
  if (n.includes("output"))
    return { key: "OUT_STRUCT", title: "Cấu trúc các địa chỉ nhận tiền", description: "Cấu trúc các đầu nhận của giao dịch là một trong những yếu tố khiến hệ thống tăng mức cảnh báo." };
  if (n.includes("input"))
    return { key: "IN_STRUCT", title: "Cấu trúc các nguồn tiền vào", description: "Cấu trúc các nguồn tiền vào của giao dịch là một trong những yếu tố khiến hệ thống tăng mức cảnh báo." };
  if (n.includes("volume"))
    return { key: "VOLUME", title: "Quy mô giá trị giao dịch", description: "Quy mô giá trị của giao dịch khác đáng kể so với nhiều giao dịch thông thường." };
  if (n.includes("fee"))
    return { key: "FEES", title: "Mức phí giao dịch", description: "Mức phí của giao dịch có đặc điểm khác đáng kể so với nhiều giao dịch thông thường." };
  return null; // time step / không xếp nhóm → bỏ khỏi lý do nghiệp vụ
}

export interface BusinessReason {
  title: string;
  description: string;
  impact: "CAO" | "TRUNG BÌNH" | "THẤP";
}

/**
 * 2–4 dấu hiệu nghiệp vụ, gộp theo nhóm, xếp theo tổng độ ảnh hưởng. Chỉ dùng
 * đặc trưng ĐÃ PHỤC HỒI (không bịa); đặc trưng chưa giải nghĩa bị bỏ qua.
 */
export function businessReasons(drivers: FcBitcoinDriver[]): BusinessReason[] {
  const agg = new Map<string, { cat: Category; weight: number }>();
  for (const d of drivers) {
    if (!d.meaningful || !d.label) continue;
    if (d.contribution <= 0) continue; // chỉ yếu tố LÀM TĂNG cảnh báo
    const cat = categoryOf(d.label);
    if (!cat) continue;
    const cur = agg.get(cat.key);
    if (cur) cur.weight += Math.abs(d.contribution);
    else agg.set(cat.key, { cat, weight: Math.abs(d.contribution) });
  }
  const ranked = [...agg.values()].sort((a, b) => b.weight - a.weight).slice(0, 4);
  return ranked.map((r, i) => ({
    title: r.cat.title,
    description: r.cat.description,
    impact: i <= 1 ? "CAO" : i === 2 ? "TRUNG BÌNH" : "THẤP",
  }));
}

/** Đề xuất rà soát nghiệp vụ (không nhắc dataset/nhãn tham chiếu). */
export function reviewSuggestions(inCount: number, outCount: number, flaggedRelated: number): string[] {
  const s: string[] = ["Kiểm tra lịch sử các địa chỉ gửi/nhận tiền liên quan tới giao dịch."];
  if (inCount > 0 || outCount > 0) s.push("Mở rộng dòng tiền trước và sau giao dịch để xem luồng tiền đi đâu.");
  if (flaggedRelated > 0) s.push(`Kiểm tra ${flaggedRelated} giao dịch liên quan đang có mức cảnh báo cao.`);
  s.push("Đối chiếu thông tin chủ thể/ví nếu có nguồn dữ liệu bổ sung.");
  s.push("Xác định có đủ căn cứ để mở vụ việc điều tra hay không.");
  return s;
}
