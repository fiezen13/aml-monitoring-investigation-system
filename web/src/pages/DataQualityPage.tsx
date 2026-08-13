import { useMemo, useState } from "react";

import { api } from "../api/client";
import { conf, int } from "../api/fcFormat";
import { formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
import { type ChartSpec } from "../components/fc/Chart";
import { ChartCard } from "../components/fc/ChartCard";
import { Chip, Empty, KpiCard, Panel, ProgressBar, ScreenTitle, Skeleton } from "../components/fc/primitives";
import { C } from "../design/palette";

/**
 * Chất lượng dữ liệu — kiểm tra chất lượng dữ liệu và nhật ký mở quyền bằng chứng.
 *
 * Hai tab tưởng như không liên quan nhưng cùng trả lời một câu hỏi: dữ liệu mà
 * mô hình đang học có đáng tin không. Tab đầu hỏi "có sạch không", tab sau hỏi
 * "có được phép nhìn thấy tại thời điểm đó không" — vế thứ hai mới là thứ làm
 * làm sai kết quả đánh giá chuẩn một cách âm thầm.
 */

const DIMENSION_LABEL: Record<string, string> = {
  completeness: "Đầy đủ",
  timeliness: "Kịp thời",
  validity: "Hợp lệ",
  consistency: "Nhất quán",
  uniqueness: "Duy nhất",
};

const STATUS_COLOR: Record<string, string> = { ok: C.ok, warn: C.warn, fail: C.risk };
const STATUS_LABEL: Record<string, string> = { ok: "Đạt", warn: "Cảnh báo", fail: "Không đạt" };

const ROLE_COLOR: Record<string, string> = {
  BANK: C.info,
  FIU: C.primary,
  REGULATOR: C.agent,
  LAW_ENFORCEMENT: C.risk,
  PUBLIC: C.ok,
};

const ROLE_LABEL: Record<string, string> = {
  BANK: "Ngân hàng",
  FIU: "FIU",
  REGULATOR: "Cơ quan quản lý",
  LAW_ENFORCEMENT: "Cơ quan điều tra",
  PUBLIC: "Công khai",
};

const ACQUISITION_LABEL: Record<string, string> = {
  native_system: "hệ thống nội bộ",
  report: "báo cáo gửi lên",
  request: "yêu cầu cung cấp",
  seizure: "thu giữ",
  cooperation: "hợp tác",
  public: "công khai",
};

const SOURCE_TYPE_LABEL: Record<string, string> = {
  bank_internal: "Nội bộ ngân hàng",
  regulatory_filing: "Hồ sơ quản lý",
  public_registry: "Cơ sở dữ liệu công khai",
  law_enforcement: "Cơ quan điều tra",
  commercial_provider: "Nhà cung cấp thương mại",
  synthetic: "Dữ liệu tổng hợp",
  legal_text: "Văn bản pháp luật",
  official_case: "Vụ án chính thức",
  public_blockchain: "Chuỗi khối công khai",
  expert_assumption: "Giả định chuyên gia",
};

function sourceTextVi(value: string): string {
  return value
    .replace(/\bhop\b/g, "chặng")
    .replace(/\bdataset\b/gi, "tập dữ liệu")
    .replace(/\bconfidence\b/gi, "độ tin cậy")
    .replace(/\bsubtitle\b/gi, "tiêu đề phụ")
    .replace(/\bblock_time\b/g, "thời điểm khối")
    .replace(/\bavailable_from\b/g, "thời điểm mở quyền")
    .replace(/\bknown_from\b/g, "thời điểm biết")
    .replace(/\bamount\b/g, "số tiền");
}

const ACCESS_LEVEL_LABEL: Record<string, string> = {
  public: "Công khai",
  restricted: "Hạn chế",
  internal: "Nội bộ",
};

const DQ_COLS = "1fr 200px 110px 110px 130px 100px";
const OBS_COLS = "110px 140px 150px 150px 90px 1fr";

export function DataQualityPage() {
  const checks = useApi(() => api.dataQuality(), []);
  const observations = useApi(() => api.observations(), []);
  const sources = useApi(() => api.sources(), []);
  const [tab, setTab] = useState<"checks" | "observations" | "sources">("checks");

  const rows = checks.data ?? [];
  const obs = observations.data ?? [];

  const failing = rows.filter((r) => r.status === "fail").length;
  const warning = rows.filter((r) => r.status === "warn").length;
  const avgPass = rows.length ? rows.reduce((s, r) => s + r.pass_rate, 0) / rows.length : 0;

  const dimensionSpec = useMemo<ChartSpec | null>(() => {
    if (!rows.length) return null;
    const byDim = new Map<string, { sum: number; n: number }>();
    for (const r of rows) {
      const cur = byDim.get(r.dimension) ?? { sum: 0, n: 0 };
      cur.sum += r.pass_rate;
      cur.n += 1;
      byDim.set(r.dimension, cur);
    }
    return {
      type: "bars",
      labels: [...byDim.keys()].map((d) => DIMENSION_LABEL[d] ?? d),
      series: [
        {
          name: "Tỷ lệ đạt (%)",
          data: [...byDim.values()].map((v) => Math.round((v.sum / v.n) * 10) / 10),
          color: C.primary,
        },
      ],
      max: 100,
      refs: [{ v: 95, label: "ngưỡng chung 95%", color: "rgba(245,165,36,0.6)" }],
    };
  }, [rows]);

  const timelineSpec = useMemo<ChartSpec | null>(() => {
    if (!obs.length) return null;
    // Số bằng chứng mở quyền theo vai trò — cho thấy tầng nào biết chuyện
    // trước, tầng nào biết sau.
    const byRole = new Map<string, number>();
    for (const o of obs) byRole.set(o.observer_role, (byRole.get(o.observer_role) ?? 0) + 1);
    return {
      type: "donut",
      items: [...byRole.entries()].map(([role, n]) => ({
        label: ROLE_LABEL[role] ?? role,
        value: n,
        color: ROLE_COLOR[role] ?? C.inkSoft,
      })),
    };
  }, [obs]);

  return (
    <div className="flex animate-up flex-col gap-3.5 p-4">
      <ScreenTitle
        title="Chất lượng dữ liệu"
        meta="Dữ liệu có sạch không, và mô hình có được phép nhìn thấy nó tại thời điểm ra quyết định không"
      />

      <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
        <KpiCard label="Kiểm tra không đạt" value={failing} valueColor={failing ? C.risk : C.ok} delta={`trên ${rows.length} kiểm tra`} />
        <KpiCard label="Cảnh báo" value={warning} valueColor={warning ? C.warn : C.inkLow} delta="sát ngưỡng" />
        <KpiCard label="Tỷ lệ đạt trung bình" value={`${avgPass.toFixed(1)}%`} valueColor={C.primary} delta="trên mọi tập dữ liệu" />
        <KpiCard label="Bằng chứng đã mở quyền" value={obs.length} valueColor={C.info} delta="theo nhật ký quan sát" />
      </div>

      <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))" }}>
        <ChartCard
          title="Tỷ lệ đạt theo chiều chất lượng"
          subtitle="Trung bình của các kiểm tra trong cùng một chiều"
          spec={dimensionSpec}
          tools={["data", "dl", "full"]}
          state={checks.loading ? "loading" : dimensionSpec ? "ok" : "empty"}
        />
        <ChartCard
          title="Bằng chứng theo vai trò quan sát"
          subtitle="Tầng nào biết trước, tầng nào biết sau"
          spec={timelineSpec}
          tools={["data", "dl"]}
          state={observations.loading ? "loading" : timelineSpec ? "ok" : "empty"}
        />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {(
          [
            ["checks", `Kiểm tra chất lượng (${rows.length})`],
            ["observations", `Nhật ký mở quyền (${obs.length})`],
            ["sources", `Danh mục nguồn (${sources.data?.length ?? 0})`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`rounded-control border px-3 py-1.5 text-base transition-colors ${
              tab === key
                ? "border-primary-line bg-primary-soft text-primary"
                : "border-line-strong/70 text-ink-soft hover:text-ink-hi"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "checks" && (
        <Panel bodyClassName="overflow-x-auto px-0">
          <div className="min-w-[880px]">
            <div
              className="grid gap-2 border-b border-line px-3 py-2 text-3xs uppercase tracking-[0.07em] text-ink-low"
              style={{ gridTemplateColumns: DQ_COLS }}
            >
              <span>Kiểm tra</span>
              <span>Tập dữ liệu</span>
              <span>Chiều</span>
              <span className="text-right">Tỷ lệ đạt</span>
              <span>Bản ghi lỗi</span>
              <span>Trạng thái</span>
            </div>
            {checks.loading && <Skeleton rows={6} />}
            {!checks.loading && !rows.length && <Empty text="Chưa có kết quả kiểm tra nào" />}
            {rows.map((r) => (
              <div
                key={r.id}
                className="grid items-center gap-2 border-b border-line-faint px-3 py-2 text-base transition-colors hover:bg-elev"
                style={{ gridTemplateColumns: DQ_COLS }}
              >
                <div className="min-w-0">
                  <div className="truncate-1 text-xs text-ink-mid">{sourceTextVi(r.check_name)}</div>
                  <ProgressBar value={r.pass_rate} color={STATUS_COLOR[r.status] ?? C.inkSoft} />
                </div>
                <span className="truncate-1 font-mono text-2xs text-ink-low">{r.dataset}</span>
                <span className="text-xs text-ink-soft">{DIMENSION_LABEL[r.dimension] ?? r.dimension}</span>
                <span className="tabular text-right font-mono text-xs" style={{ color: STATUS_COLOR[r.status] }}>
                  {r.pass_rate.toFixed(1)}%
                </span>
                <span className="tabular font-mono text-xs text-ink-soft">
                  {int(r.rows_failed)} / {int(r.rows_checked)}
                </span>
                <Chip color={STATUS_COLOR[r.status] ?? C.inkSoft}>{STATUS_LABEL[r.status] ?? r.status}</Chip>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {tab === "observations" && (
        <>
          <Panel bodyClassName="overflow-x-auto px-0">
            <div className="min-w-[920px]">
              <div
                className="grid gap-2 border-b border-line px-3 py-2 text-3xs uppercase tracking-[0.07em] text-ink-low"
                style={{ gridTemplateColumns: OBS_COLS }}
              >
                <span>Bằng chứng</span>
                <span>Vai trò quan sát</span>
                <span>Mở quyền từ</span>
                <span>Cách thu thập</span>
                <span>Độ tin cậy</span>
                <span>Nội dung</span>
              </div>
              {observations.loading && <Skeleton rows={6} />}
              {!observations.loading && !obs.length && <Empty text="Chưa có nhật ký mở quyền nào" />}
              {obs.map((o) => (
                <div
                  key={o.id}
                  className="grid items-center gap-2 border-b border-line-faint px-3 py-2 text-base transition-colors hover:bg-elev"
                  style={{ gridTemplateColumns: OBS_COLS }}
                >
                  <span className="font-mono text-xs text-primary">{o.evidence_item_id}</span>
                  <Chip color={ROLE_COLOR[o.observer_role] ?? C.inkSoft}>
                    {ROLE_LABEL[o.observer_role] ?? o.observer_role}
                  </Chip>
                  <span className="text-xs text-ink-soft">{formatDateTime(o.available_from)}</span>
                  <span className="text-xs text-ink-soft">
                    {ACQUISITION_LABEL[o.acquisition_type] ?? o.acquisition_type}
                  </span>
                  <span className="tabular font-mono text-xs">{conf(o.source_confidence)}</span>
                  <span className="truncate-1 text-xs text-ink-low" title={o.summary}>
                    {o.summary}
                    {o.legal_basis_id && (
                      <span className="ml-1 font-mono text-3xs text-agent">[{o.legal_basis_id}]</span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Vì sao nhật ký này quan trọng" subtitle="Cơ chế chống rò rỉ chính của thiết kế">
            <p className="text-xs leading-relaxed text-ink-soft">
              Một bằng chứng có thể tồn tại trong thế giới thật từ rất sớm, nhưng chỉ vào được tầm nhìn của một vai trò
              tại thời điểm nó được mở quyền — bằng hệ thống nội bộ, bằng báo cáo, bằng yêu cầu chính thức, hoặc bằng
              thu giữ khi điều tra.
            </p>
            <p className="mt-2 text-xs leading-relaxed text-ink-low">
              Nếu mô hình được huấn luyện trên bằng chứng có mốc mở quyền <b className="text-ink-mid">muộn hơn</b> thời
              điểm ra quyết định, kết quả đánh giá chuẩn sẽ đẹp một cách giả tạo và sẽ sụp khi triển khai thật. Đây là loại
              lỗi không báo lỗi — nó chỉ hiện ra khi hệ thống đã chạy trong môi trường thực.
            </p>
          </Panel>
        </>
      )}

      {tab === "sources" && (
        <div className="flex flex-col gap-2.5">
          {sources.loading && <Skeleton rows={4} />}
          {(sources.data ?? []).map((s) => (
            <Panel key={s.source_id}>
              <div className="flex flex-wrap items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-base text-primary">{s.source_id}</span>
                    <Chip color={C.agent}>{SOURCE_TYPE_LABEL[s.source_type] ?? s.source_type}</Chip>
                    <Chip color={s.access_level === "public" ? C.ok : C.warn}>{ACCESS_LEVEL_LABEL[s.access_level] ?? s.access_level}</Chip>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-ink-mid">{sourceTextVi(s.scope)}</p>
                  <p className="mt-0.5 text-2xs text-ink-low">
                    {s.jurisdiction} · {s.period}
                  </p>
                </div>
                <div className="flex-none text-right">
                  <div className="text-2xs text-ink-low">Độ tin cậy</div>
                  <div
                    className="tabular font-mono text-4xl font-semibold"
                    style={{ color: s.confidence >= 0.8 ? C.ok : s.confidence >= 0.6 ? C.warn : C.risk }}
                  >
                    {conf(s.confidence)}
                  </div>
                </div>
              </div>
              <div className="mt-2.5 rounded-control border border-risk/25 bg-risk/[0.07] px-3 py-2">
                <div className="fc-eyebrow mb-1" style={{ color: C.riskSoft }}>
                  Không được dùng để
                </div>
                <p className="text-xs leading-relaxed text-ink-soft">{sourceTextVi(s.prohibited_uses)}</p>
              </div>
            </Panel>
          ))}
        </div>
      )}
    </div>
  );
}
