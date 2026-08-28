import type { LucideIcon } from "lucide-react";
import {
  Blocks,
  ClipboardCheck,
  Coins,
  Database,
  FileCheck2,
  Gauge,
  Globe2,
  History,
  LayoutGrid,
  Receipt,
  Settings,
  Sparkles,
  Target,
  Users,
} from "lucide-react";

/**
 * Cấu trúc điều hướng của console.
 *
 * Thứ tự các nhóm theo đúng đường đi công việc của analyst: nhìn toàn cảnh →
 * xử lý cảnh báo và vụ việc → tra cứu chuyên sâu → kiểm tra chất lượng mô hình
 * → quản trị. Đặt "Chất lượng & mô hình" trước "Quản trị" là có chủ đích:
 * nó là việc hằng ngày của nhóm data, còn quản trị thì thỉnh thoảng mới vào.
 */

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Nhãn nhóm; chỉ mục đầu tiên của mỗi nhóm mới có. */
  section?: string;
  /** Khoá đếm badge lấy từ API `/nav-counts`; bỏ trống thì không hiện badge. */
  badge?: "alerts" | "approvals";
  /** Chỉ hiện với các vai trò này; bỏ trống nghĩa là mọi vai trò đều thấy. */
  roles?: string[];
}

export const NAV: NavItem[] = [
  // Ba vai trò, tách bạch NGHIỆP VỤ khỏi KỸ THUẬT:
  //
  //   analyst  Chuyên viên — rà soát cảnh báo, điều tra, dòng tiền, vụ việc.
  //            KHÔNG thấy tab kỹ thuật/mô hình.
  //   manager  Quản lý — mọi việc của Chuyên viên + soạn/duyệt SAR + phê duyệt
  //            + nhật ký kiểm toán nghiệp vụ. Vẫn KHÔNG thấy tab kỹ thuật.
  //   admin    Quản trị hệ thống — TẤT CẢ tab kỹ thuật (đánh giá chuẩn, giám sát
  //            mô hình, chất lượng dữ liệu, lượt chạy tác tử) + người dùng + cấu
  //            hình. KHÔNG ra quyết định AML, không đọc hồ sơ điều tra.
  //
  // Bỏ trống `roles` nghĩa là mọi vai trò đều thấy.

  { section: "Giám sát", to: "/dashboard", label: "Tổng quan", icon: LayoutGrid },
  { to: "/world", label: "Giám sát địa lý", icon: Globe2 },

  // Một mục điều tra duy nhất. Trang Vụ việc đã gộp: hàng đợi cảnh báo (KPI phễu)
  // + đồ thị mạng lưới của từng vụ nằm ngay trong vụ. Không còn hai mục trùng vai.
  {
    section: "Điều tra",
    to: "/cases",
    label: "Vụ việc",
    icon: ClipboardCheck,
    roles: ["analyst", "manager"],
  },
  {
    to: "/transactions",
    label: "Tra cứu giao dịch",
    icon: Receipt,
    roles: ["analyst", "manager"],
  },

  {
    section: "Tài sản mã hoá",
    to: "/crypto",
    label: "Truy vết tài sản mã hoá",
    icon: Coins,
    roles: ["analyst", "manager"],
  },

  { to: "/projects", label: "Rủi ro dự án", icon: Blocks, roles: ["analyst", "manager"] },

  // Tab KỸ THUẬT — chỉ Quản trị hệ thống (admin). Chuyên viên và Quản lý không thấy.
  {
    section: "Kỹ thuật · Mô hình",
    to: "/agents",
    label: "Lượt chạy tác tử",
    icon: Sparkles,
    roles: ["admin"],
  },
  {
    to: "/benchmarks",
    label: "Đánh giá chuẩn",
    icon: Target,
    roles: ["admin"],
  },
  {
    to: "/models",
    label: "Giám sát mô hình",
    icon: Gauge,
    roles: ["admin"],
  },
  {
    to: "/data-quality",
    label: "Chất lượng dữ liệu",
    icon: Database,
    roles: ["admin"],
  },

  {
    section: "Quản trị",
    to: "/approvals",
    label: "Phê duyệt SAR",
    icon: FileCheck2,
    badge: "approvals",
    roles: ["manager"],
  },
  { to: "/audit", label: "Nhật ký kiểm toán", icon: History, roles: ["manager", "admin"] },
  { to: "/users", label: "Người dùng", icon: Users, roles: ["admin"] },
  { to: "/settings", label: "Cấu hình", icon: Settings, roles: ["admin"] },
];
/**
 * Vai trò được vào từng route, khớp theo tiền tố (dài trước ngắn).
 *
 * `NAV` chỉ phủ các mục có trong menu; bảng này phủ cả những đường dẫn con mà
 * menu không trỏ tới — chi tiết cảnh báo, trang soạn SAR, đồ thị của một vụ
 * việc. Thiếu chúng thì việc lọc menu chỉ ẩn được lối vào, còn ai gõ thẳng URL
 * vẫn mở được màn hình.
 *
 * Đây vẫn chỉ là lớp tiện dụng. Quyết định thật nằm ở `src/api/authz.py`: dữ
 * liệu không tới thì trang có mở ra cũng trống. Giữ hai bên khớp nhau để người
 * dùng gặp màn 403 rõ ràng thay vì một trang lỗi tải.
 */
// Giữ KHỚP với ma trận quyền (src/api/permissions.py + authz.py). Ba vai trò:
// Chuyên viên (analyst) và Quản lý (manager) làm nghiệp vụ AML; tab kỹ thuật
// (tác tử / đánh giá chuẩn / mô hình / chất lượng dữ liệu) và quản trị hệ thống
// chỉ dành cho admin. Nhật ký kiểm toán: Quản lý + admin.
export const ROUTE_ROLES: [string, string[]][] = [
  ["/alerts", ["analyst", "manager"]],
  ["/cases", ["analyst", "manager"]],
  ["/network", ["analyst", "manager"]],
  ["/transactions", ["analyst", "manager"]],
  ["/crypto", ["analyst", "manager"]],
  ["/projects", ["analyst", "manager"]],
  ["/agents", ["admin"]],
  ["/benchmarks", ["admin"]],
  ["/models", ["admin"]],
  ["/data-quality", ["admin"]],
  ["/sar", ["analyst", "manager"]],
  ["/approvals", ["manager"]],
  ["/audit", ["manager", "admin"]],
  ["/users", ["admin"]],
  ["/settings", ["admin"]],
];

/**
 * Vai trò này có được mở đường dẫn này không.
 *
 * Đường dẫn không nằm trong bảng thì mở cho mọi vai trò đã đăng nhập — `/dashboard`
 * và `/world` là số liệu tổng hợp, ai cũng xem được. Khác với phía API: ở đó
 * mặc định là đóng, vì bỏ sót một endpoint là để lộ dữ liệu, còn bỏ sót một
 * route ở đây chỉ là hiển thị một trang rỗng.
 */
export function canAccess(pathname: string, role: string | undefined): boolean {
  const rule = ROUTE_ROLES.find(([prefix]) => pathname === prefix || pathname.startsWith(`${prefix}/`));
  if (!rule) return true;
  return role !== undefined && rule[1].includes(role);
}

/** Nhãn hiển thị ở breadcrumb, khớp theo tiền tố đường dẫn (dài trước ngắn). */
export const ROUTE_TITLES: [string, string][] = [
  ["/dashboard", "Tổng quan giám sát"],
  ["/world", "Giám sát địa lý"],
  ["/alerts/", "Chi tiết cảnh báo"],
  ["/alerts", "Trung tâm cảnh báo"],
  ["/cases/", "Không gian vụ việc"],
  ["/cases", "Điều tra vụ việc"],
  ["/network", "Đồ thị mạng lưới"],
  ["/transactions", "Tra cứu giao dịch"],
  ["/crypto", "Truy vết tài sản mã hoá · mô phỏng ABM"],
  ["/projects", "Rủi ro dự án · mô phỏng ABM"],
  ["/agents/", "Bảng lượt chạy tác tử · mô phỏng ABM"],
  ["/agents", "Lượt chạy tác tử AI · mô phỏng ABM"],
  ["/benchmarks", "Đánh giá chuẩn · mô phỏng ABM"],
  ["/models", "Giám sát mô hình · mô phỏng ABM"],
  ["/data-quality", "Chất lượng dữ liệu · mô phỏng ABM"],
  ["/approvals/", "Chi tiết phê duyệt"],
  ["/approvals", "Phê duyệt SAR"],
  ["/sar/", "Rà soát bản nháp SAR"],
  ["/audit", "Nhật ký kiểm toán"],
  ["/users", "Người dùng & vai trò"],
  ["/settings", "Cấu hình hệ thống"],
];
