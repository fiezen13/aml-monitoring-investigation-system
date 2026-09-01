import { useEffect, useState } from "react";

/**
 * Theo dõi một media query.
 *
 * Console này không phải ứng dụng mobile-first, nhưng bố cục ba cột cố định sẽ
 * vỡ dưới 1024px và người dùng thỉnh thoảng mở nó trên laptop nhỏ hoặc màn chia
 * đôi. Hook cho phép bố cục *đổi hình* ở các mốc ấy thay vì chỉ co lại cho tới
 * khi tràn.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const list = window.matchMedia(query);
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    setMatches(list.matches);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** Dưới mốc này, sidebar chuyển từ cột cố định sang lớp phủ. */
export const NARROW_QUERY = "(max-width: 1023px)";

export function useIsNarrow(): boolean {
  return useMediaQuery(NARROW_QUERY);
}
