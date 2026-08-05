import { useMemo, useState } from "react";

import { api } from "../api/client";
import { conf, int, shortAddr, usd } from "../api/fcFormat";
import { formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
import { type ChartSpec } from "../components/fc/Chart";
import { ChartCard } from "../components/fc/ChartCard";
import { Chip, Empty, KpiCard, Panel, ScreenTitle, Skeleton } from "../components/fc/primitives";
import { C, SERIES } from "../design/palette";

/**
 * Crypto Tracing — chuyển động on-chain và mức độ phơi nhiễm dịch vụ.
 *
 * Điểm cần giữ đúng ở màn hình này là *độ bất định*. Dữ liệu on-chain là công
 * khai và chắc chắn, nhưng việc gán một địa chỉ cho một dịch vụ, hay nối chân
 * tiền đồng với chân on-chain, đều là suy luận có xác suất. Mọi con số suy
 * luận ở đây đều đi kèm độ tin cậy, và ngôn từ dừng ở "mức độ phơi nhiễm" chứ
 * không tuyên bố đã truy ra danh tính.
 */

const TX_COLS = "150px 120px 120px 90px 110px 90px 110px";
const EXP_COLS = "150px 130px 100px 80px 110px 1fr";

const SERVICE_COLOR: Record<string, string> = {
  exchange: C.info,
  mixer: C.risk,
  bridge: C.ok,
  gambling: C.warn,
  darknet: C.risk,
  p2p: C.primary,
  sanctioned: C.risk,
};

export function CryptoPage() {
  const data = useApi(() => api.crypto(300), []);
  const [tab, setTab] = useState<"transfers" | "exposures">("transfers");

  const transfers = data.data?.transfers ?? [];
  const exposures = data.data?.exposures ?? [];

  const kpis = useMemo(() => {
    const lowConfidence = transfers.filter((t) => (t.link_confidence ?? 1) < 0.7).length;
    const indirect = exposures.filter((e) => e.exposure_kind === "indirect").length;
    return [
      { label: "Tổng giá trị on-chain", value: usd(data.data?.total_usd ?? 0), color: C.inkHi, delta: `${transfers.length} giao dịch` },
      { label: "Địa chỉ có phơi nhiễm", value: new Set(exposures.map((e) => e.address)).size, color: C.warn, delta: `${indirect} gián tiếp` },
      {
        label: "Liên kết độ tin cậy thấp",
        value: lowConfidence,
        color: C.risk,
        delta: "dưới 0.70 — không đủ để kết luận",
      },
      {
        label: "Độ tin cậy trung bình",
        value: exposures.length
          ? (exposures.reduce((s, e) => s + e.confidence, 0) / exposures.length).toFixed(2)
          : "—",
        color: C.agent,
        delta: "trên nhãn phơi nhiễm",
      },
    ];
  }, [data.data, transfers, exposures]);

  const volumeSpec = useMemo<ChartSpec | null>(() => {
    if (!transfers.length) return null;
    const byDay = new Map<string, number>();
    for (const t of transfers) {
      const key = new Date(t.block_time).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
      byDay.set(key, (byDay.get(key) ?? 0) + t.amount_usd);
    }
    const labels = [...byDay.keys()].reverse();
    return {
      type: "area",
      labels,
      series: [{ name: "Giá trị (USD)", data: labels.map((l) => Math.round(byDay.get(l)!)), color: C.primary, fill: true }],
    };
  }, [transfers]);

  const confidenceSpec = useMemo<ChartSpec | null>(() => {
    if (!transfers.length) return null;
    // Phân bố độ tin cậy của liên kết bank↔chain. Khối lượng dồn ở khoảng
    // giữa nghĩa là phần lớn kết nối chỉ là ứng viên, không phải bằng chứng.
    const buckets = [0, 0, 0, 0, 0];
    for (const t of transfers) {
      const c = t.link_confidence ?? 0;
      buckets[Math.min(4, Math.floor(c * 5))] += 1;
    }
    return {
      type: "bars",
      labels: ["0–0.2", "0.2–0.4", "0.4–0.6", "0.6–0.8", "0.8–1.0"],
      series: [
        {
          name: "Số liên kết",
          data: buckets,
          color: C.warn,
          fmt: "raw",
        },
      ],
    };
  }, [transfers]);

  const serviceSpec = useMemo<ChartSpec | null>(() => {
    if (!exposures.length) return null;
    const byType = new Map<string, number>();
    for (const e of exposures) byType.set(e.service_type, (byType.get(e.service_type) ?? 0) + 1);
    return {
      type: "donut",
      items: [...byType.entries()].map(([t, n], i) => ({
        label: t,
        value: n,
        color: SERVICE_COLOR[t] ?? SERIES[i % SERIES.length],
      })),
    };
  }, [exposures]);

  return (
    <div className="flex animate-up flex-col gap-3.5 p-4">
      <ScreenTitle
        title="Crypto Tracing"
        meta="Dữ liệu on-chain là quan sát chắc chắn; việc gán dịch vụ và nối với chân ngân hàng là suy luận có xác suất"
      />

      <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
        {data.loading
          ? Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-[76px] animate-pulse rounded-panel bg-panel" />)
          : kpis.map((k) => <KpiCard key={k.label} label={k.label} value={k.value} valueColor={k.color} delta={k.delta} />)}
      </div>

      <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(290px,1fr))" }}>
        <ChartCard
          title="Giá trị chuyển theo ngày"
          subtitle="Tổng USD quy đổi tại thời điểm khối"
          spec={volumeSpec}
          state={data.loading ? "loading" : volumeSpec ? "ok" : "empty"}
        />
        <ChartCard
          title="Độ tin cậy liên kết bank ↔ chain"
          subtitle="Phân bố — dồn ở giữa nghĩa là phần lớn chỉ là ứng viên"
          spec={confidenceSpec}
          tools={["data", "dl", "full"]}
          state={data.loading ? "loading" : confidenceSpec ? "ok" : "empty"}
          note="Liên kết dưới 0.70 không đủ làm căn cứ cho bất kỳ kết luận nào."
        />
        <ChartCard
          title="Phơi nhiễm theo loại dịch vụ"
          subtitle="Số nhãn, không phải số tiền"
          spec={serviceSpec}
          tools={["data", "dl"]}
          state={data.loading ? "loading" : serviceSpec ? "ok" : "empty"}
        />
      </div>

      <div className="flex gap-1.5">
        {(
          [
            ["transfers", `Giao dịch on-chain (${transfers.length})`],
            ["exposures", `Nhãn phơi nhiễm (${exposures.length})`],
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

      {tab === "transfers" ? (
        <Panel bodyClassName="overflow-x-auto px-0">
          <div className="min-w-[860px]">
            <div
              className="grid gap-2 border-b border-line px-3 py-2 text-3xs uppercase tracking-[0.07em] text-ink-low"
              style={{ gridTemplateColumns: TX_COLS }}
            >
              <span>Tx hash</span>
              <span>Từ địa chỉ</span>
              <span>Đến địa chỉ</span>
              <span>Tài sản</span>
              <span className="text-right">Giá trị USD</span>
              <span>Loại</span>
              <span>Độ tin cậy</span>
            </div>
            {data.loading && <Skeleton rows={8} />}
            {!data.loading && !transfers.length && <Empty text="Chưa có giao dịch on-chain nào" hint="Chạy scripts/abm_generate.py để sinh dữ liệu" />}
            {transfers.map((t) => (
              <div
                key={t.id}
                className="grid items-center gap-2 border-b border-line-faint px-3 py-[7px] text-base transition-colors hover:bg-elev"
                style={{ gridTemplateColumns: TX_COLS }}
              >
                <span className="truncate-1 font-mono text-xs text-primary" title={t.tx_hash}>
                  {shortAddr(t.tx_hash, 8, 6)}
                </span>
                <span className="font-mono text-xs" title={t.from_address}>
                  {shortAddr(t.from_address)}
                </span>
                <span className="font-mono text-xs" title={t.to_address}>
                  {shortAddr(t.to_address)}
                </span>
                <span className="text-xs text-ink-soft">{t.asset}</span>
                <span className="tabular text-right font-mono text-xs">{usd(t.amount_usd)}</span>
                <span className="text-xs text-ink-soft">{t.kind}</span>
                <span
                  className="tabular font-mono text-xs"
                  style={{ color: (t.link_confidence ?? 1) < 0.7 ? C.warn : C.ok }}
                >
                  {conf(t.link_confidence)}
                </span>
              </div>
            ))}
          </div>
        </Panel>
      ) : (
        <Panel bodyClassName="overflow-x-auto px-0">
          <div className="min-w-[820px]">
            <div
              className="grid gap-2 border-b border-line px-3 py-2 text-3xs uppercase tracking-[0.07em] text-ink-low"
              style={{ gridTemplateColumns: EXP_COLS }}
            >
              <span>Địa chỉ</span>
              <span>Dịch vụ</span>
              <span>Loại phơi nhiễm</span>
              <span>Số hop</span>
              <span>Độ tin cậy</span>
              <span>Nguồn · hiệu lực từ</span>
            </div>
            {data.loading && <Skeleton rows={6} />}
            {!data.loading && !exposures.length && <Empty text="Chưa có nhãn phơi nhiễm nào" />}
            {exposures.map((e) => (
              <div
                key={`${e.address}-${e.service_id}`}
                className="grid items-center gap-2 border-b border-line-faint px-3 py-[7px] text-base transition-colors hover:bg-elev"
                style={{ gridTemplateColumns: EXP_COLS }}
              >
                <span className="font-mono text-xs" title={e.address}>
                  {shortAddr(e.address)}
                </span>
                <Chip color={SERVICE_COLOR[e.service_type] ?? C.inkSoft}>{e.service_type}</Chip>
                <span className="text-xs text-ink-soft">
                  {e.exposure_kind === "direct" ? "trực tiếp" : "gián tiếp"}
                </span>
                <span className="tabular font-mono text-xs">{int(e.hops)}</span>
                <span
                  className="tabular font-mono text-xs"
                  style={{ color: e.confidence >= 0.75 ? C.ok : e.confidence >= 0.5 ? C.warn : C.risk }}
                >
                  {conf(e.confidence)}
                </span>
                <span className="truncate-1 text-2xs text-ink-low">
                  {e.source_id} · {formatDateTime(e.known_from)}
                </span>
              </div>
            ))}
          </div>
        </Panel>
      )}

      <Panel title="Giới hạn của phương pháp" subtitle="Phải công bố cùng mọi kết luận truy vết">
        <p className="text-xs leading-relaxed text-ink-soft">
          Agent chỉ được kết luận rằng một địa chỉ <b className="text-ink-mid">có mức độ phơi nhiễm</b> hoặc{" "}
          <b className="text-ink-mid">có đường đi phù hợp với typology</b>, kèm độ tin cậy. Không được tuyên bố đã phá
          ẩn danh một dịch vụ trộn hay xác định danh tính chủ sở hữu ví.
        </p>
        <p className="mt-2 text-xs leading-relaxed text-ink-low">
          Giao dịch tiền mặt thuần tuý và tài sản tăng cường ẩn danh không đi qua điểm on/off-ramp quan sát được sẽ tạo
          ra vùng mù không thể khắc phục bằng dữ liệu ngân hàng. Sản phẩm đo và báo cáo độ phủ, không quảng cáo phát
          hiện toàn diện.
        </p>
      </Panel>
    </div>
  );
}
