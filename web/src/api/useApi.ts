import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "./client";

export interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Gọi một endpoint và theo dõi ba trạng thái tải/lỗi/dữ liệu.
 *
 * `deps` quyết định khi nào gọi lại — dùng đúng như mảng phụ thuộc của
 * useEffect. `fetcher` cố tình không nằm trong deps: hầu hết chỗ gọi truyền
 * một arrow function mới ở mỗi lần render, đưa nó vào deps sẽ thành vòng lặp
 * vô hạn.
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    // Phản hồi tới muộn của một lần gọi đã cũ không được ghi đè kết quả mới:
    // đổi bộ lọc nhanh hai lần thì lần chậm hơn có thể về sau và thắng.
    let live = true;
    setLoading(true);
    setError(null);

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
        if (live) setLoading(false);
      });

    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  return { data, loading, error, reload };
}
