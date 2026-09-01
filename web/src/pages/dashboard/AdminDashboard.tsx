/**
 * Quản trị viên — Quản trị nền tảng.
 *
 * Câu hỏi chính: "Nền tảng AML có đang chạy, an toàn và cấu hình đúng không?"
 * Người dùng, vai trò, sức khoẻ hệ thống. ADMIN KHÔNG ra quyết định AML.
 */
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import { int } from "../../api/fcFormat";
import { formatDateTime } from "../../api/format";
import { useApi } from "../../api/useApi";
import { Chip, Empty, Panel, ScreenTitle } from "../../components/fc/primitives";
import { MetricCard, PageShell } from "../../components/ui";
import { C } from "../../design/palette";

export function AdminDashboard() {
  const users = useApi(() => api.users(), []);
  const health = useApi(() => api.ready(), []);
  const list = users.data ?? [];
  const active = list.filter((u) => u.active).length;

  return (
    <PageShell variant="dense" title="Quản trị nền tảng" subtitle="Người dùng · vai trò · hệ thống · vai trò Quản trị viên">
      <ScreenTitle title="Tình trạng hệ thống" />
      <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))" }}>
        <MetricCard label="Người dùng hoạt động" value={int(active)} tone="neutral" />
        <MetricCard label="Người dùng bị khoá" value={int(list.length - active)} tone="neutral" />
        <MetricCard label="Cơ sở dữ liệu" value={health.data?.database ? "OK" : "—"} tone={health.data?.database ? "ok" : "risk"} />
        <MetricCard label="Redis / hàng đợi" value={health.data?.redis ? "OK" : "—"} tone={health.data?.redis ? "ok" : "risk"} />
      </div>

      <Panel title="Người dùng" subtitle="Quản trị người dùng & vai trò">
        {users.loading ? (
          <Empty text="Đang tải…" />
        ) : !list.length ? (
          <Empty text="Chưa có người dùng" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-ink-dim">
                  <th className="py-1 pr-3 text-left font-medium">Tên</th>
                  <th className="py-1 pr-3 text-left font-medium">Email</th>
                  <th className="py-1 pr-3 text-left font-medium">Vai trò</th>
                  <th className="py-1 pr-3 text-left font-medium">Trạng thái</th>
                  <th className="py-1 text-left font-medium">Đăng nhập gần nhất</th>
                </tr>
              </thead>
              <tbody className="text-ink-soft">
                {list.map((u) => (
                  <tr key={u.id} className="border-t border-line-faint/60">
                    <td className="py-1 pr-3 text-ink-hi">{u.name}</td>
                    <td className="py-1 pr-3 font-mono text-2xs">{u.email}</td>
                    <td className="py-1 pr-3"><Chip color={C.info}>{u.roleLabel}</Chip></td>
                    <td className="py-1 pr-3">{u.active ? "Hoạt động" : "Khoá"}</td>
                    <td className="py-1 font-mono text-2xs text-ink-low">{u.lastLogin ? formatDateTime(u.lastLogin) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-2 text-2xs text-ink-low">
          Quản trị đầy đủ ở{" "}
          <Link to="/users" className="text-primary hover:underline">Người dùng</Link>{" "}và{" "}
          <Link to="/settings" className="text-primary hover:underline">Cấu hình</Link>.
        </div>
      </Panel>
    </PageShell>
  );
}
