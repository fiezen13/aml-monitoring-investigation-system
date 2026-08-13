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
  { section: "Giám sát", to: "/dashboard", label: "Tổng quan", icon: LayoutGrid },
  { to: "/world", label: "Giám sát địa lý", icon: Globe2 },

  { section: "Điều tra", to: "/alerts", label: "Trung tâm cảnh báo", icon: Bell, badge: "alerts" },
  { to: "/cases", label: "Vụ việc", icon: ClipboardCheck },
  { to: "/network", label: "Đồ thị mạng lưới · mô phỏng", icon: Network },
  { to: "/transactions", label: "Tra cứu giao dịch", icon: Receipt },

  { section: "Tài sản mã hoá · mô phỏng", to: "/crypto", label: "Truy vết tài sản mã hoá", icon: Coins },
  { to: "/projects", label: "Rủi ro dự án", icon: Blocks },

  { section: "Tác tử AI", to: "/agents", label: "Lượt chạy tác tử · mô phỏng", icon: Sparkles },

  { section: "Chất lượng & mô hình · mô phỏng", to: "/benchmarks", label: "Đánh giá chuẩn", icon: Target },
  { to: "/models", label: "Giám sát mô hình", icon: Gauge },
  { to: "/data-quality", label: "Chất lượng dữ liệu", icon: Database },

  { section: "Quản trị", to: "/approvals", label: "Phê duyệt SAR", icon: FileCheck2, badge: "approvals" },
  { to: "/audit", label: "Nhật ký kiểm toán", icon: History },
  { to: "/users", label: "Người dùng", icon: Users, roles: ["admin", "compliance_officer"] },
  { to: "/settings", label: "Cấu hình", icon: Settings },
];

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
