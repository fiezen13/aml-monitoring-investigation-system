import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

/**
 * Trạng thái dùng chung của cả console: bộ dữ liệu vận hành đang xem và sidebar
 * thu gọn hay không.
 *
 * Từng có thêm "cửa sổ thời gian" (1h/24h/7d/30d) và "môi trường mô phỏng". Đã gỡ
 * cả hai vì không truy vấn nào nhận: mọi số liệu trên console là tổng của một
 * lượt chạy trên một bộ dữ liệu cố định. Header giờ hiển thị đúng kỳ dữ liệu.
 *
 * Tách khỏi `AppContext` (vốn lo phiên đăng nhập và toast) vì hai nhóm này có
 * vòng đời khác nhau: đăng xuất thì xoá phiên, nhưng bộ dữ liệu người dùng vừa
 * chọn thì nên giữ lại cho lần sau.
 */

interface ConsoleState {
  /**
   * Bộ dữ liệu vận hành đang xem — chọn MỘT LẦN ở header, mọi trang dùng chung
   * (Tổng quan, Cảnh báo, Giao dịch, Vụ việc, Mạng lưới) cùng đọc. Trước đây chỉ
   * Alerts có bộ chọn riêng nên các trang khác trộn hai vũ trụ tài khoản không
   * liên quan, chuyên viên không biết mình đang nhìn bộ nào. Chỉ gồm các bộ CÓ
   * dữ liệu vận hành trong ngân hàng: nhánh Bitcoin (Elliptic) ẩn danh và tách
   * riêng ở trang Tài sản mã hoá nên không nằm ở đây.
   */
  dataset: string;
  setDataset: (d: string) => void;
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
}

/** Các bộ dữ liệu có mặt trong hàng đợi vận hành. Nhãn khớp `datasetLabel`. */
export const OPERATIONAL_DATASETS = [
  { value: "ibm_hi_medium", label: "Ngân hàng (IBM)" },
  { value: "saml_d", label: "SAML-D" },
] as const;

const ConsoleContext = createContext<ConsoleState | null>(null);

const PREF_KEY = "fin07.console.prefs";

interface Prefs {
  dataset: string;
  sidebarCollapsed: boolean;
}

const DEFAULTS: Prefs = { dataset: "ibm_hi_medium", sidebarCollapsed: false };

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
      dataset: prefs.dataset,
      setDataset: (d) => setPrefs((p) => ({ ...p, dataset: d })),
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
