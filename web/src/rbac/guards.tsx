/**
 * Bảo vệ route và hành động theo quyền.
 *
 * `RequirePermission` chặn TRUY CẬP TRỰC TIẾP bằng URL (không chỉ ẩn menu): vào
 * thẳng đường dẫn không có quyền sẽ thấy trang 403. `Can` bọc nút/hành động —
 * nhưng backend VẪN kiểm độc lập, đây chỉ là lớp phản chiếu cho người dùng.
 */
import type { ReactNode } from "react";

import { AccessDenied } from "../components/common/AccessDenied";
import type { Permission } from "./permissions";
import { useRbac } from "./useRbac";

export function RequirePermission({
  permission,
  anyOf,
  children,
}: {
  permission?: Permission;
  anyOf?: Permission[];
  children: ReactNode;
}) {
  const rbac = useRbac();
  const ok = permission ? rbac.can(permission) : anyOf ? rbac.canAny(anyOf) : false;
  return ok ? <>{children}</> : <AccessDenied />;
}

export function Can({
  permission,
  anyOf,
  fallback = null,
  children,
}: {
  permission?: Permission;
  anyOf?: Permission[];
  fallback?: ReactNode;
  children: ReactNode;
}) {
  const rbac = useRbac();
  const ok = permission ? rbac.can(permission) : anyOf ? rbac.canAny(anyOf) : false;
  return <>{ok ? children : fallback}</>;
}
