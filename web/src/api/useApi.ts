import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./client";

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
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inFlight, setInFlight] = useState(true);
  const [nonce, setNonce] = useState(0);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  // Đổi `deps` nghĩa là đổi câu hỏi — dữ liệu cũ trả lời câu khác nên phải bỏ
  // đi, nếu không màn hình sẽ hiện dữ liệu của cảnh báo trước trong một nhịp.
  // Còn `reload()` chỉ hỏi lại **cùng một câu**, nên giữ nguyên dữ liệu đang có.
  useEffect(() => {
    setData(null);
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
        if (live) setData(result);
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
