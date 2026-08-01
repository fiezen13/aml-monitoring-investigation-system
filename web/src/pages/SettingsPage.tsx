import { useState } from "react";

import { api, type ApiSetting } from "../api/client";
import { formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
import { Panel } from "../components/common/Panel";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/common/States";
import { Tooltip } from "../components/common/Tooltip";
import { PageHeader } from "../components/layout/PageHeader";
import { useApp } from "../context/AppContext";

function displayValue(setting: ApiSetting): string {
  if (setting.unit === "VNĐ") return Number(setting.value).toLocaleString("vi-VN");
  return setting.value;
}

/** Cấu hình hệ thống được đọc/ghi trực tiếp qua bảng system_setting. */
export function SettingsPage() {
  const { currentUser, pushToast } = useApp();
  const settingsQuery = useApi(() => api.settings(), []);
  const [saving, setSaving] = useState<string | null>(null);
  const canEdit = currentUser?.role === "admin" || currentUser?.role === "mlro";
  const settings = settingsQuery.data?.settings ?? [];
  const thresholds = settings.filter((setting) => setting.code !== "NOTIFY-INTERNAL");
  const notification = settings.find((setting) => setting.code === "NOTIFY-INTERNAL");
  const versions = settingsQuery.data?.watchlistVersions ?? [];

  async function save(setting: ApiSetting, value: string, reason: string) {
    try {
      setSaving(setting.code);
      await api.updateSetting(setting.code, value, reason);
      settingsQuery.reload();
      pushToast({ tone: "success", title: `Đã cập nhật ${setting.code}`, detail: "Giá trị mới và lý do đã được ghi vào audit trail." });
    } catch (cause) {
      pushToast({ tone: "error", title: "Không cập nhật được cấu hình", detail: cause instanceof Error ? cause.message : "Lỗi không xác định" });
    } finally {
      setSaving(null);
    }
  }

  function edit(setting: ApiSetting) {
    const value = window.prompt(`Giá trị mới cho ${setting.code}`, setting.value);
    if (value === null || !value.trim() || value === setting.value) return;
    const reason = window.prompt("Lý do thay đổi (tối thiểu 10 ký tự)", "Cập nhật tham số theo yêu cầu vận hành");
    if (!reason || reason.trim().length < 10) {
      pushToast({ tone: "error", title: "Lý do phải có tối thiểu 10 ký tự" });
      return;
    }
    void save(setting, value.trim(), reason.trim());
  }

  return (
    <div className="mx-auto max-w-[980px] space-y-3">
      <PageHeader title="Cấu hình hệ thống" subtitle="Tham số Risk Engine, ngưỡng cảnh báo và kênh thông báo nội bộ." />

      {settingsQuery.loading && <Panel><LoadingSkeleton rows={5} /></Panel>}
      {settingsQuery.error && <Panel><ErrorState detail={settingsQuery.error} onRetry={settingsQuery.reload} /></Panel>}
      {!settingsQuery.loading && !settingsQuery.error && (
        <>
          <Panel title="Ngưỡng Risk Engine" padded={false}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left">
                <thead><tr className="border-b border-line">{["Mã", "Tham số", "Giá trị", "Nguồn", "Cập nhật", ""].map((heading) => <th key={heading} className="px-4 py-2.5 text-2xs font-semibold uppercase tracking-wider text-ink-mid">{heading}</th>)}</tr></thead>
                <tbody>{thresholds.map((setting) => (
                  <tr key={setting.code} className="border-b border-line/60 last:border-0">
                    <td className="tabular px-4 py-2.5 text-2xs text-ink-low">{setting.code}</td>
                    <td className="px-4 py-2.5 text-[13px] text-ink-hi">{setting.label}</td>
                    <td className="tabular px-4 py-2.5 text-[13px] font-semibold text-ink-hi">{displayValue(setting)} <span className="text-2xs font-normal text-ink-low">{setting.unit}</span></td>
                    <td className="px-4 py-2.5 text-2xs text-ink-mid">{setting.source}</td>
                    <td className="tabular px-4 py-2.5 text-2xs text-ink-low">{formatDateTime(setting.updated_at)}</td>
                    <td className="px-4 py-2.5"><Tooltip content={canEdit ? "Thay đổi cần lý do và ghi vào audit trail" : "Chỉ Admin hoặc MLRO được chỉnh Risk Engine"}><button type="button" disabled={!canEdit || saving === setting.code} onClick={() => edit(setting)} className="rounded-control border border-line px-2.5 py-1 text-2xs font-medium text-ink-hi hover:border-primary/50 disabled:cursor-not-allowed disabled:opacity-40">{saving === setting.code ? "Đang lưu" : "Chỉnh"}</button></Tooltip></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </Panel>

          <div className="grid gap-3 md:grid-cols-2">
            <Panel title="Thông báo nội bộ">
              {notification ? <label className="flex items-start gap-2.5 text-[13px] text-ink-mid"><input type="checkbox" checked={notification.value === "true"} disabled={!canEdit || saving === notification.code} onChange={(event) => void save(notification, String(event.target.checked), "Cập nhật kênh thông báo nội bộ")} className="mt-0.5 accent-[#00B2A9]" /><span>{notification.label}.<span className="mt-1 block text-2xs text-ink-low">Không tồn tại kênh thông báo nào tới khách hàng đang bị điều tra (NT6).</span></span></label> : <EmptyState detail="Chưa có cấu hình thông báo." />}
            </Panel>

            <Panel title="Phiên bản danh sách đối chiếu">
              {versions.length ? <dl className="space-y-2.5 text-[13px]">{versions.slice(0, 4).map((version) => <div key={version.watchlist_version_id} className="flex items-center justify-between gap-3"><dt className="text-ink-mid">{version.provider}</dt><dd className="text-right"><span className="tabular block font-medium text-ink-hi">{version.watchlist_version_id}</span><span className="tabular block text-2xs text-ink-low">{formatDateTime(version.published_at)}</span></dd></div>)}</dl> : <EmptyState detail="Chưa nạp phiên bản danh sách đối chiếu." />}
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
