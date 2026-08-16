import type { LucideIcon } from "lucide-react";
import {
  Bell,
  Blocks,
  ClipboardCheck,
  Coins,
  Database,
  FileCheck2,
  Gauge,
  Globe2,
  History,
  LayoutGrid,
  Network,
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
  // Phân quyền theo việc, không theo cấp bậc.
  //
  //   analyst            rà soát cảnh báo và vụ việc — công việc hằng ngày
  //   compliance_officer analyst + phê duyệt SAR + quản trị người dùng
  //   mlro               người chịu trách nhiệm cuối, thấy toàn bộ
  //   auditor            CHỈ ĐỌC dấu vết: kiểm toán, mô hình, chất lượng dữ liệu.
  //                      Cố ý không thấy hàng đợi cảnh báo — kiểm toán viên rà
  //                      lại quyết định đã ra, không tham gia ra quyết định.
  //   admin              vận hành hệ thống: người dùng, cấu hình, sức khoẻ mô hình.
  //                      Cố ý không thấy dữ liệu điều tra — quản trị hạ tầng
  //                      không cần đọc hồ sơ khách hàng.
  //
  // Bỏ trống `roles` nghĩa là mọi vai trò đều thấy.

  { section: "Giám sát", to: "/dashboard", label: "Tổng quan", icon: LayoutGrid },
  { to: "/world", label: "Giám sát địa lý", icon: Globe2 },

  {
    section: "Điều tra",
    to: "/alerts",
    label: "Trung tâm cảnh báo",
    icon: Bell,
    badge: "alerts",
    roles: ["analyst", "compliance_officer", "mlro"],
  },
  { to: "/cases", label: "Vụ việc", icon: ClipboardCheck, roles: ["analyst", "compliance_officer", "mlro"] },
  {
    to: "/network",
    label: "Đồ thị mạng lưới",
    icon: Network,
    roles: ["analyst", "compliance_officer", "mlro"],
  },
  {
    to: "/transactions",
    label: "Tra cứu giao dịch",
    icon: Receipt,
    roles: ["analyst", "compliance_officer", "mlro", "auditor"],
  },

  {
    section: "Tài sản mã hoá",
    to: "/crypto",
    label: "Truy vết tài sản mã hoá",
    icon: Coins,
    roles: ["analyst", "compliance_officer", "mlro"],
  },
  { to: "/projects", label: "Rủi ro dự án", icon: Blocks, roles: ["analyst", "compliance_officer", "mlro"] },

  {
    section: "Tác tử AI",
    to: "/agents",
    label: "Lượt chạy tác tử",
    icon: Sparkles,
    roles: ["analyst", "compliance_officer", "mlro", "auditor"],
  },

  {
    section: "Chất lượng & mô hình",
    to: "/benchmarks",
    label: "Đánh giá chuẩn",
    icon: Target,
    roles: ["compliance_officer", "mlro", "auditor", "admin"],
  },
  {
    to: "/models",
    label: "Giám sát mô hình",
    icon: Gauge,
    roles: ["compliance_officer", "mlro", "auditor", "admin"],
  },
  {
    to: "/data-quality",
    label: "Chất lượng dữ liệu",
    icon: Database,
    roles: ["compliance_officer", "mlro", "auditor", "admin"],
  },

  {
    section: "Quản trị",
    to: "/approvals",
    label: "Phê duyệt SAR",
    icon: FileCheck2,
    badge: "approvals",
    roles: ["compliance_officer", "mlro"],
  },
  { to: "/audit", label: "Nhật ký kiểm toán", icon: History, roles: ["compliance_officer", "mlro", "auditor", "admin"] },
  { to: "/users", label: "Người dùng", icon: Users, roles: ["admin", "compliance_officer"] },
  { to: "/settings", label: "Cấu hình", icon: Settings, roles: ["admin", "mlro"] },
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
export const ROUTE_ROLES: [string, string[]][] = [
  ["/alerts", ["analyst", "compliance_officer", "mlro"]],
  ["/cases", ["analyst", "compliance_officer", "mlro"]],
  ["/network", ["analyst", "compliance_officer", "mlro"]],
  ["/transactions", ["analyst", "compliance_officer", "mlro", "auditor"]],
  ["/crypto", ["analyst", "compliance_officer", "mlro"]],
  ["/projects", ["analyst", "compliance_officer", "mlro"]],
  ["/agents", ["analyst", "compliance_officer", "mlro", "auditor"]],
  ["/benchmarks", ["compliance_officer", "mlro", "auditor", "admin"]],
  ["/models", ["compliance_officer", "mlro", "auditor", "admin"]],
  ["/data-quality", ["compliance_officer", "mlro", "auditor", "admin"]],
  ["/sar", ["compliance_officer", "mlro"]],
  ["/approvals", ["compliance_officer", "mlro"]],
  ["/audit", ["compliance_officer", "mlro", "auditor", "admin"]],
  ["/users", ["admin", "compliance_officer"]],
  ["/settings", ["admin", "mlro"]],
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
  ["/network", "Đồ thị mạng lưới · mô phỏng ABM"],
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
