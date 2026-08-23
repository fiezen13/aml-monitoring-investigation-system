import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./client";
import { readCache, writeCache } from "./swrCache";

export interface ApiState<T> {
  data: T | null;
  /** Chưa có gì để hiển thị và đang tải — đây mới là lúc nên vẽ khung chờ. */
  loading: boolean;
  /** Đang tải, nhưng đã có dữ liệu cũ trên màn hình. Dùng cho chỉ báo nhỏ. */
  refreshing: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Gọi một endpoint và theo dõi trạng thái tải/lỗi/dữ liệu.
 *
 * `deps` quyết định khi nào gọi lại — dùng đúng như mảng phụ thuộc của
 * useEffect. `fetcher` cố tình không nằm trong deps: hầu hết chỗ gọi truyền
 * một arrow function mới ở mỗi lần render, đưa nó vào deps sẽ thành vòng lặp
 * vô hạn.
 *
 * Phân biệt `loading` với `refreshing` là điểm mấu chốt, không phải chi tiết
 * trang trí. Màn hình điều tra hỏi lại máy chủ mỗi hai giây trong lúc tác tử
 * chạy. Nếu mỗi lượt hỏi đều bật `loading`, chỗ gọi sẽ thay toàn bộ nội dung
 * bằng khung chờ hai giây một lần — người dùng thấy màn hình giật liên tục suốt
 * cả phút. `loading` vì vậy chỉ bật khi **chưa có gì để hiển thị**.
 */
export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  cacheKey?: string,
): ApiState<T> {
  // Nạp bản cũ ngay từ lần render đầu: có cache thì `data` khác null nên
  // `loading` = false, màn hình hiện dữ liệu cũ thay vì khung chờ khi F5.
  const [data, setData] = useState<T | null>(() => (cacheKey ? readCache<T>(cacheKey) : null));
  const [error, setError] = useState<string | null>(null);
  const [inFlight, setInFlight] = useState(true);
  const [nonce, setNonce] = useState(0);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const cacheKeyRef = useRef(cacheKey);
  cacheKeyRef.current = cacheKey;

  // Đổi `deps` nghĩa là đổi câu hỏi — dữ liệu cũ trả lời câu khác nên phải bỏ
  // đi, nếu không màn hình sẽ hiện dữ liệu của cảnh báo trước trong một nhịp.
  // Có cacheKey thì thay bằng bản cũ của ĐÚNG khoá mới (nếu có) chứ không để
  // trắng — vẫn giữ cảm giác tức thì khi quay lại bộ lọc đã từng xem.
  // Còn `reload()` chỉ hỏi lại **cùng một câu**, nên giữ nguyên dữ liệu đang có.
  useEffect(() => {
    setData(cacheKey ? readCache<T>(cacheKey) : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    // Phản hồi tới muộn của một lần gọi đã cũ không được ghi đè kết quả mới:
    // đổi bộ lọc nhanh hai lần thì lần chậm hơn có thể về sau và thắng.
    let live = true;
    setError(null);
    setInFlight(true);

    fetcherRef
      .current()
      .then((result) => {
        if (!live) return;
        setData(result);
        // Ghi bản mới để lần F5 sau vẽ được ngay. Dùng ref vì cacheKey có thể
        // đã đổi trong lúc chờ phản hồi (đổi bộ lọc nhanh).
        if (cacheKeyRef.current) writeCache(cacheKeyRef.current, result);
      })
      .catch((cause: unknown) => {
        if (!live) return;
        setError(cause instanceof ApiError ? cause.message : "Lỗi không xác định");
      })
      .finally(() => {
        if (live) setInFlight(false);
      });

    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  return {
    data,
    loading: inFlight && data === null,
    refreshing: inFlight && data !== null,
    error,
    reload,
  };
}
