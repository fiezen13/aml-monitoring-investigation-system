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
  { to: "/world", label: "World Monitor", icon: Globe2 },

  { section: "Điều tra", to: "/alerts", label: "Alert Center", icon: Bell, badge: "alerts" },
  { to: "/cases", label: "Vụ việc", icon: ClipboardCheck },
  { to: "/network", label: "Network Graph", icon: Network },
  { to: "/transactions", label: "Transaction Explorer", icon: Receipt },

  { section: "Tài sản mã hoá", to: "/crypto", label: "Crypto Tracing", icon: Coins },
  { to: "/projects", label: "Project Risk", icon: Blocks },

  { section: "AI Agent", to: "/agents", label: "Agent Runs", icon: Sparkles },

  { section: "Chất lượng & mô hình", to: "/benchmarks", label: "Benchmarks", icon: Target },
  { to: "/models", label: "Model Monitoring", icon: Gauge },
  { to: "/data-quality", label: "Data Quality", icon: Database },

  { section: "Quản trị", to: "/approvals", label: "Phê duyệt SAR", icon: FileCheck2, badge: "approvals" },
  { to: "/audit", label: "Audit Logs", icon: History },
  { to: "/users", label: "Người dùng", icon: Users, roles: ["admin", "compliance_officer"] },
  { to: "/settings", label: "Cấu hình", icon: Settings },
];

/** Nhãn hiển thị ở breadcrumb, khớp theo tiền tố đường dẫn (dài trước ngắn). */
export const ROUTE_TITLES: [string, string][] = [
  ["/dashboard", "Tổng quan giám sát"],
  ["/world", "World Monitor"],
  ["/alerts/", "Chi tiết cảnh báo"],
  ["/alerts", "Alert Center"],
  ["/cases/", "Case workspace"],
  ["/cases", "Case Investigation"],
  ["/network", "Network Graph"],
  ["/transactions", "Transaction Explorer"],
  ["/crypto", "Crypto Tracing"],
  ["/projects", "Project Risk"],
  ["/agents/", "Agent Run Console"],
  ["/agents", "AI Agent Runs"],
  ["/benchmarks", "Benchmarks"],
  ["/models", "Model Monitoring"],
  ["/data-quality", "Data Quality"],
  ["/approvals/", "Chi tiết phê duyệt"],
  ["/approvals", "Phê duyệt SAR"],
  ["/sar/", "Rà soát bản nháp SAR"],
  ["/audit", "Audit Logs"],
  ["/users", "Người dùng & vai trò"],
  ["/settings", "System Settings"],
];
