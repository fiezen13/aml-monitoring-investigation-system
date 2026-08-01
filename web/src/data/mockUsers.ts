import type { Role, User } from "../types";

/** 5 người dùng demo — nhất quán trên mọi màn hình (mục 7 đề bài). */
export const USERS: User[] = [
  {
    id: "U-001",
    name: "Nguyễn Quang Hưng",
    email: "hung.nq@velrix.vn",
    role: "compliance_officer",
    roleLabel: "Compliance Officer",
    active: true,
    lastLogin: "08:12 AM, Hôm nay",
  },
  {
    id: "U-002",
    name: "Trần Hoàng Quân",
    email: "quan.th@velrix.vn",
    role: "compliance_officer",
    roleLabel: "Compliance Officer",
    active: true,
    lastLogin: "09:03 AM, Hôm nay",
  },
  {
    id: "U-003",
    name: "Đàm Minh Tuấn",
    email: "tuan.dm@velrix.vn",
    role: "mlro",
    roleLabel: "MLRO",
    active: true,
    lastLogin: "10:45 AM, Hôm nay",
  },
  {
    id: "U-004",
    name: "Lê Minh Khiêm",
    email: "khiem.lm@velrix.vn",
    role: "auditor",
    roleLabel: "Auditor",
    active: true,
    lastLogin: "2 ngày trước",
  },
  {
    id: "U-005",
    name: "Đinh Huy Mạnh",
    email: "manh.dh@velrix.vn",
    role: "admin",
    roleLabel: "Administrator",
    active: true,
    lastLogin: "07:55 AM, Hôm nay",
  },
];

/** Người dùng phụ hiển thị trong bảng Người dùng & Vai trò. */
export const EXTRA_USERS: User[] = [
  {
    id: "U-006",
    name: "Lê Anh Tuấn",
    email: "tuan.la@velrix.vn",
    role: "analyst",
    roleLabel: "Senior Analyst",
    active: false,
    lastLogin: "2 ngày trước",
  },
  {
    id: "U-007",
    name: "Phạm Văn Vĩnh",
    email: "vinh.pv@velrix.vn",
    role: "analyst",
    roleLabel: "Analyst",
    active: false,
    lastLogin: "1 tuần trước",
  },
];

export interface PermissionRow {
  action: string;
  admin: boolean;
  mlro: boolean;
  analyst: boolean;
}

/** Ma trận phân quyền — khớp screenshot Người dùng & Vai trò. */
export const PERMISSION_MATRIX: PermissionRow[] = [
  { action: "Xem báo cáo SAR", admin: true, mlro: true, analyst: true },
  { action: "Phê duyệt vụ việc", admin: true, mlro: true, analyst: false },
  { action: "Xóa log hệ thống", admin: false, mlro: false, analyst: false },
  { action: "Quản lý User", admin: true, mlro: false, analyst: false },
  { action: "Cấu hình Risk Engine", admin: true, mlro: true, analyst: false },
];

export const ROLE_HOME: Record<Role, string> = {
  compliance_officer: "/dashboard",
  mlro: "/approvals",
  auditor: "/audit",
  admin: "/users",
  analyst: "/alerts",
};
