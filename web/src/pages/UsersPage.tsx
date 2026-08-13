import { Check, Download, KeyRound, LogIn, Pencil, ShieldAlert, UserPlus, X } from "lucide-react";
import { useMemo, useState } from "react";

import { api } from "../api/client";
import { auditEventLabel, formatDateTime, formatRelative, roleLabel } from "../api/format";
import { useApi } from "../api/useApi";
import { RoleBadge, StatusBadge } from "../components/common/Badges";
import { Panel } from "../components/common/Panel";
import { ReasonModal } from "../components/common/ReasonModal";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/common/States";
import { useApp } from "../context/AppContext";
import type { User } from "../types";

const PERMISSION_MATRIX = [
  { action: "Xem báo cáo SAR", admin: true, mlro: true, analyst: true },
  { action: "Phê duyệt vụ việc", admin: true, mlro: true, analyst: false },
  { action: "Xóa nhật ký hệ thống", admin: false, mlro: false, analyst: false },
  { action: "Quản lý người dùng", admin: true, mlro: false, analyst: false },
  { action: "Cấu hình bộ máy rủi ro", admin: true, mlro: true, analyst: false },
] as const;

function downloadUsers(users: User[]) {
  const escape = (value: string) => `"${value.replaceAll('"', '""')}"`;
  const rows = users.map((user) =>
    [user.id, user.name, user.email, user.role, user.active ? "active" : "inactive", user.lastLogin ?? ""]
      .map(escape)
      .join(","),
  );
  const csv = ["id,name,email,role,status,last_login", ...rows].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "users.csv";
  link.click();
  URL.revokeObjectURL(url);
}

/** Quản trị người dùng với dữ liệu và hoạt động đọc trực tiếp từ PostgreSQL. */
export function UsersPage() {
  const { currentUser, pushToast } = useApp();
  const usersQuery = useApi(() => api.users(), []);
  const auditQuery = useApi(() => api.audit({ limit: 100 }), []);
  const [role, setRole] = useState("");
  const [editing, setEditing] = useState<User | null>(null);
  const users = usersQuery.data ?? [];
  const filteredUsers = useMemo(
    () => users.filter((user) => !role || user.role === role),
    [role, users],
  );
  const userEvents = (auditQuery.data ?? [])
    .filter((event) => ["user_login", "user_changed"].includes(event.event_type))
    .slice(0, 3);

  const kpis = [
    { label: "Tổng người dùng", value: users.length, note: "Tài khoản trong cơ sở dữ liệu", tone: "text-ink-mid" },
    { label: "Đang hoạt động", value: users.filter((user) => user.active).length, note: "Có thể đăng nhập", tone: "text-ok" },
    { label: "Đã vô hiệu hóa", value: users.filter((user) => !user.active).length, note: "Không thể đăng nhập", tone: "text-risk" },
    { label: "Vai trò", value: new Set(users.map((user) => user.role)).size, note: "Phân quyền hiện tại", tone: "text-warn" },
  ];

  return (
    <div className="mx-auto max-w-[1280px] space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-bold text-ink-hi">Quản trị Người dùng & Vai trò</h1>
          <p className="mt-0.5 text-[13px] text-ink-mid">Quản lý tài khoản, phân quyền và giám sát hoạt động hệ thống.</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => downloadUsers(filteredUsers)} disabled={!filteredUsers.length} className="inline-flex items-center gap-1.5 rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs font-medium text-ink-hi disabled:opacity-40">
            <Download size={12} aria-hidden /> Xuất báo cáo
          </button>
          <button type="button" disabled title="Tài khoản mới được cấp qua quy trình cấp quyền" className="inline-flex items-center gap-1.5 rounded-control bg-primary px-2.5 py-1.5 text-2xs font-semibold text-app disabled:cursor-not-allowed disabled:opacity-40">
            <UserPlus size={12} aria-hidden /> Thêm người dùng mới
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="rounded-panel border border-line bg-panel p-4">
            <div className="text-2xs font-semibold uppercase tracking-wider text-ink-mid">{kpi.label}</div>
            <div className="mt-1.5 flex items-end justify-between">
              <span className="tabular text-[26px] font-bold leading-none text-ink-hi">{kpi.value}</span>
              <span className={`text-2xs font-medium ${kpi.tone}`}>{kpi.note}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-3 xl:grid-cols-[1fr_380px]">
        <Panel padded={false} title="Danh sách người dùng" action={
          <label className="flex items-center gap-1.5 text-2xs text-ink-low">Lọc theo vai trò:
            <select value={role} onChange={(event) => setRole(event.target.value)} className="rounded-control border border-line bg-elev px-1.5 py-1 text-2xs text-ink-hi focus:outline-none">
              <option value="">Tất cả</option><option value="admin">Quản trị viên</option><option value="mlro">MLRO</option><option value="compliance_officer">Chuyên viên tuân thủ</option><option value="analyst">Chuyên viên phân tích</option><option value="auditor">Kiểm toán viên</option>
            </select>
          </label>
        }>
          {usersQuery.loading && <div className="p-4"><LoadingSkeleton rows={5} /></div>}
          {usersQuery.error && <div className="p-4"><ErrorState detail={usersQuery.error} onRetry={usersQuery.reload} /></div>}
          {!usersQuery.loading && !usersQuery.error && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-left">
                <thead><tr className="border-b border-line">{["Người dùng", "Vai trò", "Trạng thái", "Đăng nhập cuối", ""].map((heading) => <th key={heading} className="px-3 py-2.5 text-2xs font-semibold uppercase tracking-wider text-ink-mid">{heading}</th>)}</tr></thead>
                <tbody>
                  {filteredUsers.map((user) => (
                    <tr key={user.id} className="border-b border-line/60 last:border-0">
                      <td className="px-3 py-2.5"><span className="flex items-center gap-2"><span className="flex h-7 w-7 items-center justify-center rounded-full bg-elev text-2xs font-bold text-primary">{user.name.split(" ").slice(-2).map((word) => word[0]).join("")}</span><span><span className="block text-[13px] font-medium text-ink-hi">{user.name}</span><span className="block text-2xs text-ink-low">{user.email}</span></span></span></td>
                      <td className="px-3 py-2.5"><RoleBadge label={roleLabel(user.role)} /></td>
                      <td className="px-3 py-2.5">{user.active ? <StatusBadge tone="ok" label="Hoạt động" /> : <StatusBadge tone="risk" label="Vô hiệu hóa" />}</td>
                      <td className="tabular px-3 py-2.5 text-2xs text-ink-mid" title={formatDateTime(user.lastLogin)}>{user.lastLogin ? formatRelative(user.lastLogin) : "Chưa đăng nhập"}</td>
                      <td className="px-3 py-2.5"><button type="button" aria-label={`Đổi trạng thái ${user.name}`} disabled={currentUser?.role !== "admin"} onClick={() => setEditing(user)} className="rounded p-1.5 text-ink-low hover:bg-elev hover:text-ink-hi disabled:cursor-not-allowed disabled:opacity-30"><Pencil size={13} /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!filteredUsers.length && <div className="p-4"><EmptyState detail="Không có người dùng khớp bộ lọc." /></div>}
            </div>
          )}
        </Panel>

        <Panel padded={false} title="Ma trận Phân quyền">
          <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr className="border-b border-line"><th className="px-3 py-2.5 text-2xs font-semibold uppercase tracking-wider text-ink-mid">Hành động \ Vai trò</th>{["Quản trị viên", "MLRO", "Chuyên viên phân tích"].map((item) => <th key={item} className="px-2 py-2.5 text-center text-2xs font-semibold uppercase tracking-wider text-ink-mid">{item}</th>)}</tr></thead><tbody>{PERMISSION_MATRIX.map((row) => <tr key={row.action} className="border-b border-line/60 last:border-0"><td className="px-3 py-2.5 text-[13px] text-ink-hi">{row.action}</td>{[row.admin, row.mlro, row.analyst].map((allowed, index) => <td key={index} className="px-2 py-2.5 text-center"><span className={`inline-flex h-5 w-5 items-center justify-center rounded-full ${allowed ? "bg-ok/15 text-ok" : "bg-ink-low/10 text-ink-low"}`}>{allowed ? <Check size={11} /> : <X size={11} />}</span></td>)}</tr>)}</tbody></table></div>
          <p className="border-t border-line p-3 text-2xs leading-relaxed text-ink-mid">ⓘ Đây là chính sách phân quyền của hệ thống; mọi thay đổi tài khoản đều ghi vào nhật ký kiểm toán.</p>
        </Panel>
      </div>

      <Panel title="Hoạt động Người dùng gần đây" action={<a href="/audit" className="text-2xs font-medium text-info-soft hover:underline">Xem toàn bộ nhật ký kiểm toán ›</a>}>
        {auditQuery.loading && <LoadingSkeleton rows={3} />}
        {!auditQuery.loading && !userEvents.length && <EmptyState detail="Chưa có hoạt động người dùng." />}
        <div className="grid gap-3 md:grid-cols-3">{userEvents.map((event) => {
          const Icon = event.event_type === "user_login" ? LogIn : event.payload.after === false ? ShieldAlert : KeyRound;
          return <div key={event.audit_id} className="rounded-control border border-line bg-elev p-3"><div className="flex items-center gap-1.5 text-[13px] font-semibold text-primary"><Icon size={13} />{auditEventLabel(event.event_type)}</div><p className="mt-1 text-2xs leading-relaxed text-ink-mid">{event.actor} · {JSON.stringify(event.payload)}</p><div className="mt-1.5 text-2xs text-ink-low">{formatRelative(event.occurred_at)}</div></div>;
        })}</div>
      </Panel>

      <ReasonModal open={Boolean(editing)} title={editing?.active ? "Vô hiệu hóa tài khoản" : "Kích hoạt tài khoản"} description={`Thay đổi trạng thái ${editing?.name ?? ""}; thao tác được ghi vào nhật ký kiểm toán.`} confirmLabel={editing?.active ? "Vô hiệu hóa" : "Kích hoạt"} onClose={() => setEditing(null)} onConfirm={async (reason) => {
        if (!editing) return;
        try { await api.updateUser(editing.id, !editing.active, reason); setEditing(null); usersQuery.reload(); auditQuery.reload(); pushToast({ tone: "success", title: "Đã cập nhật trạng thái tài khoản" }); }
        catch (cause) { pushToast({ tone: "error", title: "Không cập nhật được tài khoản", detail: cause instanceof Error ? cause.message : "Lỗi không xác định" }); }
      }} />
    </div>
  );
}
