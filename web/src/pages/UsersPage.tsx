import {
  Check,
  Download,
  KeyRound,
  LogIn,
  Pencil,
  ShieldAlert,
  UserPlus,
  X,
} from "lucide-react";

import { RoleBadge, StatusBadge } from "../components/common/Badges";
import { Panel } from "../components/common/Panel";
import { useApp } from "../context/AppContext";
import { EXTRA_USERS, PERMISSION_MATRIX, USERS } from "../data/mockUsers";

const ACTIVITY = [
  {
    icon: KeyRound,
    tone: "text-warn",
    title: "Thay đổi quyền hạn",
    detail: "Đinh Huy Mạnh đã cấp quyền Phê duyệt SAR cho Nguyễn Quang Hưng.",
    time: "12 phút trước",
  },
  {
    icon: LogIn,
    tone: "text-ok",
    title: "Đăng nhập hệ thống",
    detail: "Đàm Minh Tuấn vừa đăng nhập thành công từ IP 192.168.1.45.",
    time: "45 phút trước",
  },
  {
    icon: ShieldAlert,
    tone: "text-risk",
    title: "Khóa tài khoản",
    detail: "Tài khoản Phạm Văn Vĩnh tự động bị khóa do nhập sai mật khẩu 5 lần.",
    time: "2 giờ trước",
  },
];

/** Quản trị Người dùng & Vai trò — khớp screenshot cùng tên. */
export function UsersPage() {
  const { pushToast } = useApp();
  const allUsers = [...USERS, ...EXTRA_USERS].slice(0, 5);

  return (
    <div className="mx-auto max-w-[1280px] space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-bold text-ink-hi">Quản trị Người dùng & Vai trò</h1>
          <p className="mt-0.5 text-[13px] text-ink-mid">
            Quản lý tài khoản, phân quyền và giám sát hoạt động hệ thống.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => pushToast({ tone: "success", title: "Đã xuất báo cáo người dùng (mô phỏng)" })}
            className="inline-flex items-center gap-1.5 rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs font-medium text-ink-hi"
          >
            <Download size={12} aria-hidden />
            Xuất báo cáo
          </button>
          <button
            type="button"
            onClick={() => pushToast({ tone: "info", title: "Thêm người dùng (mô phỏng)", detail: "Cần phê duyệt từ cấp cao hơn — ghi vào audit trail." })}
            className="inline-flex items-center gap-1.5 rounded-control bg-primary px-2.5 py-1.5 text-2xs font-semibold text-app hover:bg-primary-hover"
          >
            <UserPlus size={12} aria-hidden />
            Thêm người dùng mới
          </button>
        </div>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {[
          { label: "Tổng người dùng", value: "124", note: "↗ 2%", noteTone: "text-ok" },
          { label: "Đang hoạt động", value: "98", note: "79% công suất", noteTone: "text-ink-mid" },
          { label: "Phiên đăng nhập lỗi", value: "12", note: "Cần kiểm tra", noteTone: "text-risk" },
          { label: "Yêu cầu phê duyệt", value: "05", note: "Chờ xử lý", noteTone: "text-warn" },
        ].map((kpi) => (
          <div key={kpi.label} className="rounded-panel border border-line bg-panel p-4">
            <div className="text-2xs font-semibold uppercase tracking-wider text-ink-mid">
              {kpi.label}
            </div>
            <div className="mt-1.5 flex items-end justify-between">
              <span className="tabular text-[26px] font-bold leading-none text-ink-hi">
                {kpi.value}
              </span>
              <span className={`text-2xs font-medium ${kpi.noteTone}`}>{kpi.note}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-3 xl:grid-cols-[1fr_380px]">
        {/* Danh sách người dùng */}
        <Panel
          padded={false}
          title="Danh sách người dùng"
          action={
            <label className="flex items-center gap-1.5 text-2xs text-ink-low">
              Lọc theo vai trò:
              <select className="rounded-control border border-line bg-elev px-1.5 py-1 text-2xs text-ink-hi focus:outline-none">
                <option>Tất cả</option>
                <option>MLRO</option>
                <option>Compliance Officer</option>
                <option>Analyst</option>
              </select>
            </label>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left">
              <thead>
                <tr className="border-b border-line">
                  {["Người dùng", "Vai trò", "Trạng thái", "Đăng nhập cuối", ""].map((h, i) => (
                    <th
                      key={i}
                      className="px-3 py-2.5 text-2xs font-semibold uppercase tracking-wider text-ink-mid"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allUsers.map((user) => (
                  <tr key={user.id} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2.5">
                      <span className="flex items-center gap-2">
                        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-elev text-2xs font-bold text-primary">
                          {user.name
                            .split(" ")
                            .slice(-2)
                            .map((w) => w[0])
                            .join("")}
                        </span>
                        <span>
                          <span className="block text-[13px] font-medium text-ink-hi">
                            {user.name}
                          </span>
                          <span className="block text-2xs text-ink-low">{user.email}</span>
                        </span>
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <RoleBadge label={user.roleLabel} />
                    </td>
                    <td className="px-3 py-2.5">
                      {user.active ? (
                        <StatusBadge tone="ok" label="Hoạt động" />
                      ) : user.lastLogin.includes("tuần") ? (
                        <StatusBadge tone="risk" label="Bị khóa" />
                      ) : (
                        <StatusBadge tone="warn" label="Vắng mặt" />
                      )}
                    </td>
                    <td className="tabular px-3 py-2.5 text-2xs text-ink-mid">{user.lastLogin}</td>
                    <td className="px-3 py-2.5">
                      <button
                        type="button"
                        aria-label={`Sửa ${user.name}`}
                        onClick={() =>
                          pushToast({
                            tone: "info",
                            title: "Chỉnh sửa người dùng (mô phỏng)",
                            detail: "Mọi thay đổi quyền cần phê duyệt và ghi audit.",
                          })
                        }
                        className="rounded p-1.5 text-ink-low hover:bg-elev hover:text-ink-hi"
                      >
                        <Pencil size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-line py-2.5 text-center">
            <button type="button" className="text-2xs font-medium text-primary hover:underline">
              Xem thêm 120 người dùng...
            </button>
          </div>
        </Panel>

        {/* Ma trận phân quyền */}
        <Panel
          padded={false}
          title="Ma trận Phân quyền"
          action={
            <button type="button" className="text-2xs font-semibold uppercase tracking-wide text-primary hover:underline">
              Chi tiết quyền
            </button>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-line">
                  <th className="px-3 py-2.5 text-2xs font-semibold uppercase tracking-wider text-ink-mid">
                    Hành động \ Vai trò
                  </th>
                  {["Admin", "MLRO", "Analyst"].map((r) => (
                    <th
                      key={r}
                      className="px-2 py-2.5 text-center text-2xs font-semibold uppercase tracking-wider text-ink-mid"
                    >
                      {r}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {PERMISSION_MATRIX.map((row) => (
                  <tr key={row.action} className="border-b border-line/60 last:border-0">
                    <td className="px-3 py-2.5 text-[13px] text-ink-hi">{row.action}</td>
                    {[row.admin, row.mlro, row.analyst].map((allowed, i) => (
                      <td key={i} className="px-2 py-2.5 text-center">
                        {allowed ? (
                          <span
                            className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-ok/15 text-ok"
                            title="Được phép"
                          >
                            <Check size={11} aria-hidden />
                          </span>
                        ) : (
                          <span
                            className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-ink-low/10 text-ink-low"
                            title="Bị khóa — không thể tự cấp"
                          >
                            <X size={11} aria-hidden />
                          </span>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="border-t border-line p-3 text-2xs leading-relaxed text-ink-mid">
            ⓘ Mọi thay đổi trong Ma trận phân quyền sẽ được ghi lại trong Audit Trail và
            yêu cầu phê duyệt từ cấp cao hơn.
          </p>
        </Panel>
      </div>

      {/* Hoạt động gần đây */}
      <Panel
        title="Hoạt động Người dùng gần đây"
        action={
          <a href="/audit" className="text-2xs font-medium text-primary hover:underline">
            Xem toàn bộ Audit Trail ›
          </a>
        }
      >
        <div className="grid gap-3 md:grid-cols-3">
          {ACTIVITY.map(({ icon: Icon, tone, title, detail, time }) => (
            <div key={title} className="rounded-control border border-line bg-elev p-3">
              <div className={`flex items-center gap-1.5 text-[13px] font-semibold ${tone}`}>
                <Icon size={13} aria-hidden />
                {title}
              </div>
              <p className="mt-1 text-2xs leading-relaxed text-ink-mid">{detail}</p>
              <div className="mt-1.5 text-2xs text-ink-low">{time}</div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
