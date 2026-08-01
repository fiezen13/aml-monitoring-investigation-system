import { useState } from "react";

import { PageHeader } from "../components/layout/PageHeader";
import { Panel } from "../components/common/Panel";
import { Tooltip } from "../components/common/Tooltip";
import { useApp } from "../context/AppContext";

interface ThresholdRow {
  code: string;
  label: string;
  value: string;
  unit: string;
  source: string;
}

const THRESHOLDS: ThresholdRow[] = [
  {
    code: "T01-AMT",
    label: "Ngưỡng báo cáo giao dịch tiền mặt",
    value: "200,000,000",
    unit: "VNĐ",
    source: "Quy định nội bộ QD3",
  },
  {
    code: "T01-VEL",
    label: "Số giao dịch tối đa / 2 giờ trước khi cảnh báo",
    value: "10",
    unit: "giao dịch",
    source: "Risk Engine · rule",
  },
  {
    code: "SCR-TH",
    label: "Ngưỡng điểm đối chiếu danh sách",
    value: "0.75",
    unit: "điểm",
    source: "Screening Service",
  },
  {
    code: "SLA-ALERT",
    label: "SLA xử lý cảnh báo rủi ro cao",
    value: "4",
    unit: "giờ",
    source: "Quy định nội bộ QD6",
  },
];

/** Cấu hình hệ thống — chỉ Admin/MLRO chỉnh được Risk Engine (ma trận quyền). */
export function SettingsPage() {
  const { currentUser, pushToast } = useApp();
  const canEdit = currentUser?.role === "admin" || currentUser?.role === "mlro";
  const [notifyInternal, setNotifyInternal] = useState(true);

  return (
    <div className="mx-auto max-w-[980px] space-y-3">
      <PageHeader
        title="Cấu hình hệ thống"
        subtitle="Tham số Risk Engine, ngưỡng cảnh báo và kênh thông báo nội bộ."
      />

      <Panel title="Ngưỡng Risk Engine" padded={false}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left">
            <thead>
              <tr className="border-b border-line">
                {["Mã", "Tham số", "Giá trị", "Nguồn", ""].map((h, i) => (
                  <th
                    key={i}
                    className="px-4 py-2.5 text-2xs font-semibold uppercase tracking-wider text-ink-mid"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {THRESHOLDS.map((row) => (
                <tr key={row.code} className="border-b border-line/60 last:border-0">
                  <td className="tabular px-4 py-2.5 text-2xs text-ink-low">{row.code}</td>
                  <td className="px-4 py-2.5 text-[13px] text-ink-hi">{row.label}</td>
                  <td className="tabular px-4 py-2.5 text-[13px] font-semibold text-ink-hi">
                    {row.value} <span className="text-2xs font-normal text-ink-low">{row.unit}</span>
                  </td>
                  <td className="px-4 py-2.5 text-2xs text-ink-mid">{row.source}</td>
                  <td className="px-4 py-2.5">
                    <Tooltip
                      content={
                        canEdit
                          ? "Thay đổi cần lý do và ghi vào audit trail"
                          : "Chỉ Admin hoặc MLRO được chỉnh Risk Engine (ma trận phân quyền)"
                      }
                    >
                      <button
                        type="button"
                        disabled={!canEdit}
                        onClick={() =>
                          pushToast({
                            tone: "info",
                            title: "Chỉnh ngưỡng (mô phỏng)",
                            detail: "Thay đổi cấu hình yêu cầu lý do bắt buộc.",
                          })
                        }
                        className="rounded-control border border-line px-2.5 py-1 text-2xs font-medium text-ink-hi hover:border-primary/50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Chỉnh
                      </button>
                    </Tooltip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid gap-3 md:grid-cols-2">
        <Panel title="Thông báo nội bộ">
          <label className="flex items-start gap-2.5 text-[13px] text-ink-mid">
            <input
              type="checkbox"
              checked={notifyInternal}
              onChange={(e) => setNotifyInternal(e.target.checked)}
              className="mt-0.5 accent-[#00B2A9]"
            />
            <span>
              Gửi thông báo cảnh báo rủi ro cao tới kênh nội bộ của đội Compliance.
              <span className="mt-1 block text-2xs text-ink-low">
                Không tồn tại kênh thông báo nào tới khách hàng đang bị điều tra (NT6).
              </span>
            </span>
          </label>
        </Panel>

        <Panel title="Phiên bản danh sách đối chiếu">
          <dl className="space-y-2.5 text-[13px]">
            <div className="flex items-center justify-between">
              <dt className="text-ink-mid">Danh sách trừng phạt UN</dt>
              <dd className="tabular font-medium text-ink-hi">UN-2026-05</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-ink-mid">Danh sách PEP quốc gia</dt>
              <dd className="tabular font-medium text-ink-hi">PEP-VN-2026-04</dd>
            </div>
            <div className="flex items-center justify-between">
              <dt className="text-ink-mid">Nguồn đối chiếu</dt>
              <dd className="text-2xs text-ink-mid">Screening Service · SCREEN-021</dd>
            </div>
          </dl>
        </Panel>
      </div>
    </div>
  );
}
