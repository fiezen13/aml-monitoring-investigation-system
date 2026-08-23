/**
 * Cache "stale-while-revalidate" cho các màn hình đọc nhiều.
 *
 * Vấn đề: mỗi lần F5 (tải lại trình duyệt) toàn bộ state React bị xoá, mọi hook
 * gọi lại API từ đầu và người dùng nhìn khung chờ 0,6–1,6s. Với dữ liệu tổng hợp
 * (tổng quan, giám sát địa lý, số badge…) câu trả lời gần như không đổi giữa hai
 * lần tải liền nhau, nên ta lưu lại kết quả và **vẽ ngay bản cũ** trong lúc gọi
 * lại nền để làm mới.
 *
 * Vì sao `sessionStorage` chứ không phải bộ nhớ:
 *   * sessionStorage sống qua F5 nhưng mất khi đóng tab — đúng bằng vòng đời của
 *     token (cũng nằm ở sessionStorage), nên không lo rò dữ liệu sang phiên khác.
 *   * bộ nhớ (Map) thì F5 là mất, không giải quyết được đúng vấn đề reload.
 *
 * An toàn theo người dùng: token nằm cùng sessionStorage, nhưng hai người khác
 * vai trò thấy dữ liệu khác nhau. Nên phải XOÁ sạch cache khi đăng nhập/đăng
 * xuất (gọi `clearApiCache()` ở AppContext) — nếu không, người đăng nhập sau có
 * thể thấy thoáng qua số liệu của người trước.
 */

const NS = "fin07.swr.";

/** Đọc bản đã lưu cho một khoá; trả null nếu chưa có hoặc hỏng. */
export function readCache<T>(key: string): T | null {
  try {
    const raw = window.sessionStorage.getItem(NS + key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    // JSON hỏng hoặc sessionStorage bị chặn — coi như chưa có cache.
    return null;
  }
}

/** Ghi kết quả mới cho một khoá; nuốt lỗi quota để không làm hỏng luồng tải. */
export function writeCache<T>(key: string, value: T): void {
  try {
    window.sessionStorage.setItem(NS + key, JSON.stringify(value));
  } catch {
    // Vượt quota hoặc storage bị chặn — bỏ qua, coi như không có cache.
  }
}

/** Xoá toàn bộ cache SWR. Gọi khi đăng nhập/đăng xuất để không lẫn dữ liệu. */
export function clearApiCache(): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < window.sessionStorage.length; i += 1) {
      const k = window.sessionStorage.key(i);
      if (k && k.startsWith(NS)) keys.push(k);
    }
    for (const k of keys) window.sessionStorage.removeItem(k);
  } catch {
    // Không truy cập được storage — không có gì để xoá.
  }
}
