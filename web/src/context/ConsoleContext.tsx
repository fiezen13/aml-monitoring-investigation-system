import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

/**
 * Trạng thái dùng chung của cả console: cửa sổ thời gian, thế giới mô phỏng
 * đang xem, và sidebar thu gọn hay không.
 *
 * Tách khỏi `AppContext` (vốn lo phiên đăng nhập và toast) vì hai nhóm này có
 * vòng đời khác nhau: đăng xuất thì xoá phiên, nhưng cửa sổ thời gian người
 * dùng vừa chọn thì nên giữ lại cho lần sau.
 */

export type TimeWindow = "1h" | "24h" | "7d" | "30d";

export const WINDOW_LABEL: Record<TimeWindow, string> = {
  "1h": "1 giờ",
  "24h": "24 giờ",
  "7d": "7 ngày",
  "30d": "30 ngày",
};

/** Số giờ tương ứng — dùng để gửi xuống API. */
export const WINDOW_HOURS: Record<TimeWindow, number> = {
  "1h": 1,
  "24h": 24,
  "7d": 168,
  "30d": 720,
};

interface ConsoleState {
  window: TimeWindow;
  setWindow: (w: TimeWindow) => void;
  world: string;
  setWorld: (w: string) => void;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
}

const ConsoleContext = createContext<ConsoleState | null>(null);

const PREF_KEY = "fin07.console.prefs";

interface Prefs {
  window: TimeWindow;
  world: string;
  sidebarCollapsed: boolean;
}

const DEFAULTS: Prefs = { window: "24h", world: "FIN-07 Primary", sidebarCollapsed: false };

function readPrefs(): Prefs {
  try {
    const raw = window.localStorage.getItem(PREF_KEY);
    if (!raw) return DEFAULTS;
    // Ghi đè lên mặc định chứ không tin nguyên object đọc được: bản lưu từ
    // phiên bản cũ có thể thiếu trường mới thêm.
    return { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Prefs>) };
  } catch {
    return DEFAULTS;
  }
}

export function ConsoleProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<Prefs>(readPrefs);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    try {
      window.localStorage.setItem(PREF_KEY, JSON.stringify(prefs));
    } catch {
      // Chế độ riêng tư chặn localStorage. Mất tuỳ chọn thì chấp nhận được,
      // sập cả console thì không.
    }
  }, [prefs]);

  // ⌘K / Ctrl-K mở bảng lệnh ở bất kỳ màn hình nào.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const value = useMemo<ConsoleState>(
    () => ({
      window: prefs.window,
      setWindow: (w) => setPrefs((p) => ({ ...p, window: w })),
      world: prefs.world,
      setWorld: (w) => setPrefs((p) => ({ ...p, world: w })),
      sidebarCollapsed: prefs.sidebarCollapsed,
      toggleSidebar: () => setPrefs((p) => ({ ...p, sidebarCollapsed: !p.sidebarCollapsed })),
      paletteOpen,
      setPaletteOpen,
    }),
    [prefs, paletteOpen],
  );

  return <ConsoleContext.Provider value={value}>{children}</ConsoleContext.Provider>;
}

export function useConsole(): ConsoleState {
  const ctx = useContext(ConsoleContext);
  if (!ctx) throw new Error("useConsole phải được dùng bên trong ConsoleProvider");
  return ctx;
}

/** Hook tiện dụng cho các trang chỉ cần số giờ để gọi API. */
export function useWindowHours(): number {
  return WINDOW_HOURS[useConsole().window];
}
