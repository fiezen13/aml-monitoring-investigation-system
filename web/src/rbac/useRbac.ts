/**
 * Hook RBAC giao diện — kiểm quyền dựa trên `user.permissions` từ máy chủ.
 *
 * KHÔNG kiểm theo `user.role`; luôn dùng danh sách quyền do `/auth/me` cấp. Nhờ
 * vậy khi backend đổi bảng quyền, giao diện tự đúng theo mà không cần sửa mã.
 */
import { useMemo } from "react";

import { useApp } from "../context/AppContext";
import type { DataScope } from "../types";
import type { Permission } from "./permissions";

export interface Rbac {
  can: (permission: Permission) => boolean;
  canAny: (permissions: Permission[]) => boolean;
  canAll: (permissions: Permission[]) => boolean;
  dataScope: DataScope;
  role: string | null;
}

export function useRbac(): Rbac {
  const { currentUser } = useApp();
  return useMemo(() => {
    const granted = new Set(currentUser?.permissions ?? []);
    // Mặc định TỪ CHỐI: chưa đăng nhập / thiếu quyền → false.
    const can = (permission: Permission) => granted.has(permission);
    return {
      can,
      canAny: (perms) => perms.some(can),
      canAll: (perms) => perms.every(can),
      dataScope: currentUser?.dataScope ?? "assigned",
      role: currentUser?.role ?? null,
    };
  }, [currentUser]);
}
