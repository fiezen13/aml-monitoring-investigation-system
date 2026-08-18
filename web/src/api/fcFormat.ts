/** Định dạng cho dữ liệu ABM.
 *
 * Tách khỏi `format.ts` vì hai nhóm khác quy ước: các endpoint cũ trả số
 * thập phân dạng chuỗi, còn `fc_routes.py` đã ép sang number.
 */

/** Rút gọn tiền tệ theo cách bảng tài chính quen đọc: 1.2K, 3.4M, 1.05B. */
export function money(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const a = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (a >= 1e9) return `${sign}${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}${Math.round(a / 1e3)}K`;
  return `${sign}${a.toFixed(0)}`;
}

export function usd(value: number | null | undefined): string {
  return value == null ? "—" : `$${money(value)}`;
}

/** Số nguyên có dấu phân cách nghìn theo kiểu Việt Nam. */
export function int(value: number | null | undefined): string {
  return value == null ? "—" : value.toLocaleString("vi-VN");
}

/** Tỷ lệ 0–1 thành phần trăm. `digits` mặc định 0 vì bảng thường không cần lẻ. */
export function pct(value: number | null | undefined, digits = 0): string {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

/** Độ tin cậy 0–1 giữ hai chữ số — 0.79 và 0.8 là hai mức khác nhau. */
export function conf(value: number | null | undefined): string {
  return value == null ? "—" : value.toFixed(2);
}

/** Rút gọn địa chỉ ví/hash: giữ đầu và đuôi, bỏ khúc giữa. */
export function shortAddr(addr: string, head = 6, tail = 4): string {
  return addr.length <= head + tail + 1 ? addr : `${addr.slice(0, head)}…${addr.slice(-tail)}`;
}

/** Chỉ giờ:phút — dùng cho dòng thời gian dày đặc, ngày đã ghi ở chỗ khác. */
export function hhmm(iso: string): string {
  return new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

export function dayMonth(iso: string): string {
  return new Date(iso).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

/** Thời lượng mili giây thành chuỗi đọc được: 240ms, 1.9s, 3m 02s. */
export function duration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.round((ms % 60_000) / 1000);
  return `${m}m ${String(s).padStart(2, "0")}s`;
}


/** Thời lượng theo PHÚT thành chuỗi đọc được.
 *
 * Tên khác `duration` ở trên: hàm kia nhận mili giây và dùng cho độ trễ kỹ
 * thuật. Đây là quãng thời gian nghiệp vụ — "12289 phút" không ai nhẩm được là
 * 8,5 ngày, mà đó chính là thứ chuyên viên cần để đánh giá tốc độ luân chuyển.
 */
export function durationMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || minutes <= 0) return "cùng thời điểm";
  if (minutes < 60) return `${Math.round(minutes)} phút`;
  if (minutes < 60 * 24) {
    const hours = minutes / 60;
    return `${hours.toFixed(hours < 10 ? 1 : 0)} giờ`;
  }
  const days = minutes / (60 * 24);
  return `${days.toFixed(days < 10 ? 1 : 0)} ngày`;
}
