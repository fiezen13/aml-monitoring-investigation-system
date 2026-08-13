import { Database, MapPinOff, Maximize2, Pause, Play } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { int, usd } from "../api/fcFormat";
import { riskRatingLabel } from "../api/format";
import { useApi } from "../api/useApi";
import { Chart, type ChartSpec } from "../components/fc/Chart";
import { Eyebrow, PulseDot, StatTile } from "../components/fc/primitives";
import { WorldMap, type MapData } from "../components/fc/WorldMap";
import { C, CHANNEL, CHANNEL_LABEL } from "../design/palette";

/**
 * World Monitor — bản đồ dòng tiền toàn cầu.
 *
 * Ba cột: bộ lọc bên trái, bản đồ ở giữa, inspector và luồng sự kiện bên phải;
 * dải phân tích ở dưới cùng thu gọn được. Bản đồ và quả cầu 3D là engine canvas
 * lấy nguyên từ prototype (`src/vendor/fc/`), nhận dữ liệu qua property.
 */

const CHANNELS = ["bank", "p2p", "vasp", "chain", "gamb", "proj"] as const;
const SEVERITIES = [
  { key: "all", label: "Tất cả" },
  { key: "warn", label: "Đáng ngờ" },
  { key: "crit", label: "Nghiêm trọng" },
];
const SPEEDS = [0.5, 1, 2];
const TOP_N = [10, 25, 50];

function hubNameVi(name: string): string {
  const labels: Record<string, string> = {
    Bangkok: "Băng Cốc",
    "Hong Kong": "Hồng Kông",
    "Phnom Penh": "Phnôm Pênh",
  };
  return labels[name] ?? name;
}

/** Engine bản đồ phân loại mức độ theo ba bậc, suy từ điểm rủi ro của hành lang. */
function severityOf(risk: number): "crit" | "warn" | "ok" {
  return risk >= 80 ? "crit" : risk >= 60 ? "warn" : "ok";
}

export function WorldPage() {
  const [dataMode, setDataMode] = useState<"operational" | "simulation">("operational");
  const world = useApi(() => api.world(dataMode), [dataMode]);

  const [mode, setMode] = useState<"map" | "globe">("map");
  const [layers, setLayers] = useState<Record<string, boolean>>(
    Object.fromEntries(CHANNELS.map((c) => [c, true])),
  );
  const [sev, setSev] = useState("all");
  const [typ, setTyp] = useState("all");
  const [topN, setTopN] = useState(25);
  const [hideNormal, setHideNormal] = useState(false);
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [replayT, setReplayT] = useState(100);
  const [bottomOpen, setBottomOpen] = useState(true);
  const [selFlow, setSelFlow] = useState<string | null>(null);
  const [selHub, setSelHub] = useState<string | null>(null);

  // Chuyển hợp đồng API sang hình dạng mà engine canvas mong đợi. Giữ phép
  // chuyển ở một chỗ để engine không phải biết gì về API, và ngược lại.
  const mapData = useMemo<MapData | null>(() => {
    if (!world.data) return null;
    return {
      hubs: world.data.hubs.map((h) => ({
        id: h.id,
        name: hubNameVi(h.name),
        lat: h.lat,
        lon: h.lon,
        // Kích thước chấm theo khối lượng, thang log: chênh lệch giữa các
        // trung tâm là vài bậc độ lớn, thang tuyến tính sẽ chỉ thấy một chấm to.
        size: Math.max(1.2, Math.min(3, Math.log10(Math.max(10, h.volume_usd)) / 3)),
        vol: usd(h.volume_usd),
        entities: h.entities,
        alerts: h.alerts,
        inb: h.inbound,
        outb: h.outbound,
        cases: h.alerts,
        riskN: h.risk_score,
      })),
      flows: world.data.flows.map((f, i) => ({
        id: f.id,
        sn: hubNameVi(f.source_name),
        tn: hubNameVi(f.target_name),
        slat: f.slat,
        slon: f.slon,
        tlat: f.tlat,
        tlon: f.tlon,
        ch: f.channel,
        risk: severityOf(f.risk_score),
        vol: usd(f.volume_usd),
        txn: f.txn_count,
        typ: f.typology_hint,
        riskN: f.risk_score,
        cur: f.currency,
        // Lệch pha để các hạt trên những cung khác nhau không chạy trùng nhịp.
        t0: ((i * 7) % 21) / 20,
        ph: ((i * 13) % 17) / 17,
        alertN: f.alert_count,
        cases: [],
        status: f.risk_score >= 80 ? "ĐANG ĐIỀU TRA" : f.risk_score >= 60 ? "THEO DÕI" : "BÌNH THƯỜNG",
      })),
    };
  }, [world.data]);

  const typologies = useMemo(() => {
    const counts = new Map<string, number>();
    for (const f of world.data?.flows ?? []) {
      if (f.typology_hint) counts.set(f.typology_hint, (counts.get(f.typology_hint) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [world.data]);

  const stats = useMemo(() => {
    const flows = world.data?.flows ?? [];
    const total = flows.reduce((s, f) => s + f.volume_usd, 0);
    const susp = flows.filter((f) => f.risk_score >= 60);
    const crit = flows.filter((f) => f.risk_score >= 80);
    return [
      { l: "Tổng khối lượng", v: usd(total), c: C.inkHi, d: `${flows.length} hành lang` },
      { l: "Đáng ngờ", v: usd(susp.reduce((s, f) => s + f.volume_usd, 0)), c: C.warn, d: `${susp.length} hành lang` },
      { l: "Nghiêm trọng", v: String(crit.length), c: C.risk, d: "cần xử lý ngay" },
      { l: "Giao dịch", v: int(flows.reduce((s, f) => s + f.txn_count, 0)), c: C.inkHi, d: "trong cửa sổ" },
      { l: "Cảnh báo", v: String(flows.reduce((s, f) => s + f.alert_count, 0)), c: C.risk, d: "trên hành lang" },
      { l: "Trung tâm", v: String(world.data?.hubs.length ?? 0), c: C.info, d: "đang theo dõi" },
    ];
  }, [world.data]);

  const selected = world.data?.flows.find((f) => f.id === selFlow) ?? null;
  const selectedHub = world.data?.hubs.find((h) => h.id === selHub) ?? null;

  // --- các biểu đồ ở dải dưới ---

  const channelMixSpec = useMemo<ChartSpec | null>(() => {
    const flows = world.data?.flows;
    if (!flows?.length) return null;
    const byCh = new Map<string, number>();
    for (const f of flows) byCh.set(f.channel, (byCh.get(f.channel) ?? 0) + f.volume_usd);
    return {
      type: "donut",
      items: [...byCh.entries()].map(([ch, v]) => ({
        label: CHANNEL_LABEL[ch] ?? ch,
        value: Math.round(v / 1e6),
        color: CHANNEL[ch],
      })),
    };
  }, [world.data]);

  const corridorRankSpec = useMemo<ChartSpec | null>(() => {
    const flows = world.data?.flows;
    if (!flows?.length) return null;
    const top = [...flows].sort((a, b) => b.volume_usd - a.volume_usd).slice(0, 8);
    return {
      type: "hbars",
      items: top.map((f) => ({
        label: `${hubNameVi(f.source_name).slice(0, 12)} → ${hubNameVi(f.target_name).slice(0, 12)}`,
        value: Math.round(f.volume_usd / 1e6),
        color: f.risk_score >= 80 ? C.risk : f.risk_score >= 60 ? C.warn : C.info,
      })),
    };
  }, [world.data]);

  const riskByChannelSpec = useMemo<ChartSpec | null>(() => {
    const flows = world.data?.flows;
    if (!flows?.length) return null;
    const chans = [...new Set(flows.map((f) => f.channel))];
    return {
      type: "bars",
      labels: chans.map((c) => CHANNEL_LABEL[c] ?? c),
      series: [
        {
          name: "Rủi ro cao nhất",
          data: chans.map((c) => Math.max(...flows.filter((f) => f.channel === c).map((f) => f.risk_score))),
          color: C.warn,
        },
      ],
    };
  }, [world.data]);

  if (!world.loading && world.data?.data_mode === "operational" && !world.data.geography_available) {
    return (
      <div className="flex h-full min-w-0 flex-col overflow-y-auto bg-app p-5">
        <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-4">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line pb-4">
            <div>
              <Eyebrow className="mb-2">Giám sát địa lý · dữ liệu vận hành</Eyebrow>
              <h1 className="text-2xl font-semibold text-ink-hi">Không đủ dữ liệu để dựng bản đồ địa lý</h1>
              <p className="mt-2 max-w-[760px] text-sm leading-relaxed text-ink-soft">
                Hệ thống không suy diễn quốc gia hoặc toạ độ từ mã ngân hàng. Vì vậy bản đồ được chủ động tắt thay vì
                ghép lô dữ liệu IBM với kịch bản Việt Nam không liên quan.
              </p>
            </div>
            <span className="flex items-center gap-2 rounded-chip border border-warn/35 bg-warn/10 px-3 py-1.5 text-xs text-warn-soft">
              <MapPinOff size={14} /> Chưa có dữ liệu địa lý đã kiểm chứng
            </span>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-[12px] border border-line bg-panel p-4 md:col-span-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-ink-hi">
                <Database size={15} className="text-primary" /> Nguồn đang hoạt động
              </div>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-xs text-ink-low">Tệp nguồn</dt>
                  <dd className="mt-1 font-mono text-ink-mid">{world.data.source_name ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-low">Mã lô dữ liệu</dt>
                  <dd className="mt-1 font-mono text-ink-mid">{world.data.source_id ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-low">Giao dịch đã nạp</dt>
                  <dd className="mt-1 font-mono text-xl font-semibold text-ink-hi">
                    {int(world.data.transaction_count)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-ink-low">Phạm vi địa lý</dt>
                  <dd className="mt-1 font-medium text-warn-soft">Không được cung cấp</dd>
                </div>
              </dl>
            </div>

            <div className="rounded-[12px] border border-line bg-side p-4">
              <div className="text-sm font-semibold text-ink-hi">Giới hạn dữ liệu</div>
              <p className="mt-3 text-xs leading-relaxed text-ink-soft">{world.data.limitation}</p>
              <p className="mt-3 text-xs leading-relaxed text-ink-low">
                Mã ngân hàng trong IBM AML là mã định danh của tập dữ liệu, không phải mã quốc gia và không đủ để đặt một
                điểm lên bản đồ.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[12px] border border-line bg-side p-4">
            <div>
              <div className="text-sm font-semibold text-ink-hi">Dữ liệu giao dịch vẫn xem được đầy đủ</div>
              <p className="mt-1 text-xs text-ink-soft">
                Tra cứu giao dịch đọc trực tiếp bảng giao dịch và gồm cả giao dịch dưới ngưỡng ML hành vi.
              </p>
            </div>
            <div className="flex gap-2">
              <Link to="/transactions" className="fc-btn">
                Mở Tra cứu giao dịch
              </Link>
              <button type="button" onClick={() => setDataMode("simulation")} className="fc-btn">
                Xem riêng mô phỏng ABM
              </button>
            </div>
          </div>

          <p className="text-2xs leading-relaxed text-ink-low">
            Chế độ mô phỏng ABM là dữ liệu tổng hợp phục vụ minh hoạ/đánh giá chuẩn. Nó được tách khỏi nguồn vận hành và không
            đại diện cho địa lý của tệp IBM.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden">
      <div className="flex min-h-0 flex-1 overflow-x-auto">
        {/* --- Cột trái: bộ lọc --- */}
        <aside className="flex min-w-[216px] flex-[0_3_300px] flex-col gap-3.5 overflow-y-auto border-r border-line bg-side p-3.5">
          {/* Hai nguồn dữ liệu, hai cảnh báo khác nhau. Trước khi địa lý vận hành
              chạy được, thân trang này chỉ hiện ở chế độ mô phỏng nên nhãn ABM
              gắn cứng cũng không sai; giờ thì sai, vì bản đồ vận hành dùng chung
              thân trang. */}
          {dataMode === "simulation" ? (
            <div className="rounded-[9px] border border-warn/30 bg-warn/10 p-2.5">
              <div className="text-3xs font-semibold uppercase tracking-[0.09em] text-warn-soft">Mô phỏng ABM</div>
              <p className="mt-1 text-2xs leading-relaxed text-ink-soft">
                Kịch bản tổng hợp Việt Nam, tách biệt với lô giao dịch vận hành.
              </p>
              <button type="button" onClick={() => setDataMode("operational")} className="fc-btn mt-2 w-full">
                Quay lại dữ liệu vận hành
              </button>
            </div>
          ) : (
            <div className="rounded-[9px] border border-line bg-panel p-2.5">
              <div className="text-3xs font-semibold uppercase tracking-[0.09em] text-ink-dim">Dữ liệu vận hành</div>
              <p className="mt-1 text-2xs leading-relaxed text-ink-soft">{world.data?.limitation}</p>
              <button type="button" onClick={() => setDataMode("simulation")} className="fc-btn mt-2 w-full">
                Xem riêng mô phỏng ABM
              </button>
            </div>
          )}
          <div>
            <Eyebrow className="mb-2">Chỉ số mô phỏng toàn cầu</Eyebrow>
            <div className="grid grid-cols-2 gap-[7px]">
              {stats.map((s) => (
                <StatTile key={s.l} label={s.l} value={s.v} sub={s.d} valueColor={s.c} />
              ))}
            </div>
          </div>

          <div>
            <Eyebrow className="mb-2">Các lớp dòng tiền</Eyebrow>
            <div className="flex flex-col gap-1">
              {CHANNELS.map((ch) => (
                <button
                  key={ch}
                  type="button"
                  onClick={() => setLayers((l) => ({ ...l, [ch]: !l[ch] }))}
                  aria-pressed={layers[ch]}
                  className="flex items-center gap-2.5 rounded-control px-2 py-1.5 text-base transition-colors hover:bg-elev"
                >
                  <span className="h-[9px] w-[9px] flex-none rounded-sm" style={{ background: CHANNEL[ch] }} />
                  <span className="flex-1 text-left text-ink-mid">{CHANNEL_LABEL[ch]}</span>
                  {/* Công tắc mang màu của chính lớp đó, không phải màu accent
                      chung: sáu công tắc cùng một sắc teal thì chỉ nói được
                      "đang bật", còn ở đây chúng nói luôn "đang bật cái gì". */}
                  <span
                    className="relative h-[14px] w-[30px] flex-none rounded-full border border-line-strong transition-colors"
                    style={{ background: layers[ch] ? `${CHANNEL[ch]}2E` : "transparent" }}
                  >
                    <span
                      className="absolute top-[1.5px] h-[9px] w-[9px] rounded-full transition-[left]"
                      style={{ left: layers[ch] ? 18 : 2, background: layers[ch] ? CHANNEL[ch] : C.inkDim }}
                    />
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <Eyebrow className="mb-2">Mức độ</Eyebrow>
            <div className="flex gap-1">
              {SEVERITIES.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => setSev(s.key)}
                  className={`flex-1 rounded-control border py-1 text-xs transition-colors ${
                    sev === s.key
                      ? "border-primary-line bg-primary-soft text-primary"
                      : "border-line-strong/70 text-ink-soft hover:text-ink-hi"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          {typologies.length > 0 && (
            <div>
              <Eyebrow className="mb-2">Nhóm hành vi</Eyebrow>
              <div className="flex flex-col gap-[3px]">
                <button
                  type="button"
                  onClick={() => setTyp("all")}
                  className={`flex items-center gap-2 rounded-[7px] px-2 py-1.5 text-sm transition-colors hover:bg-elev ${
                    typ === "all" ? "bg-primary-soft text-primary" : "text-ink-soft"
                  }`}
                >
                  <span className="flex-1 text-left">Tất cả nhóm hành vi</span>
                </button>
                {typologies.map(([t, n]) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTyp(t)}
                    className={`flex items-center gap-2 rounded-[7px] px-2 py-1.5 text-sm transition-colors hover:bg-elev ${
                      typ === t ? "bg-primary-soft text-primary" : "text-ink-soft"
                    }`}
                  >
                    <span className="h-[7px] w-[7px] flex-none rounded-sm bg-risk" />
                    <span className="truncate-1 flex-1 text-left">{t}</span>
                    <span className="tabular flex-none font-mono text-2xs text-ink-low">{n}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <p className="border-t border-line-soft pt-2.5 text-2xs leading-relaxed text-ink-low">
            Kéo để xoay · cuộn để phóng · rê chuột lên cung để xem chi tiết · nhấp vào cung hoặc trung tâm để mở
            bảng thanh tra · nháy đúp nền để đặt lại. Đây là dữ liệu tổng hợp từ mô phỏng ABM, không phải lô dữ liệu IBM.
          </p>
        </aside>

        {/* --- Cột giữa: bản đồ --- */}
        <div
          className="relative min-w-[390px] flex-[1_1_480px] overflow-hidden"
          style={{ background: "radial-gradient(ellipse at 50% 42%,#0D1B26 0%,#080D12 72%)" }}
        >
          <WorldMap
            data={mapData}
            mode={mode}
            layers={layers}
            sev={sev}
            typ={typ}
            topN={topN}
            hideNormal={hideNormal}
            selectedFlow={selFlow}
            selectedHub={selHub}
            onPickFlow={setSelFlow}
            onPickHub={setSelHub}
          />

          <div className="absolute left-3.5 top-3 z-[4] flex items-center gap-2 rounded-chip border border-line bg-side/85 px-3 py-1 text-2xs backdrop-blur">
            <PulseDot color={world.error ? C.risk : C.ok} />
            <span className="font-mono tracking-[0.08em]" style={{ color: world.error ? C.risk : C.ok }}>
              {world.error
                ? "MẤT KẾT NỐI"
                : world.loading
                  ? "ĐANG TẢI"
                  : dataMode === "simulation"
                    ? "MÔ PHỎNG ABM"
                    : "DỮ LIỆU VẬN HÀNH"}
            </span>
          </div>

          <div className="absolute right-3 top-2.5 z-[4] flex items-center gap-1.5">
            <div className="flex gap-0.5 rounded-control border border-line bg-side/85 p-0.5 backdrop-blur">
              {(["map", "globe"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  className={`rounded-[6px] px-2.5 py-1 text-xs transition-colors ${
                    mode === m ? "bg-primary-soft text-primary" : "text-ink-soft hover:text-ink-hi"
                  }`}
                >
                  {m === "map" ? "2D" : "3D"}
                </button>
              ))}
            </div>
            <div className="flex gap-0.5 rounded-control border border-line bg-side/85 p-0.5 backdrop-blur">
              {TOP_N.map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setTopN(n)}
                  className={`rounded-[6px] px-2 py-1 text-xs transition-colors ${
                    topN === n ? "bg-primary-soft text-primary" : "text-ink-soft hover:text-ink-hi"
                  }`}
                >
                  Top {n}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setHideNormal((v) => !v)}
              title="Chỉ hiện dòng tiền đáng ngờ"
              className={`rounded-control border px-2.5 py-1 text-xs backdrop-blur transition-colors ${
                hideNormal
                  ? "border-primary-line bg-primary-soft text-primary"
                  : "border-line-strong bg-side/85 text-ink-soft hover:text-ink-hi"
              }`}
            >
              Chỉ đáng ngờ
            </button>
          </div>

          {selected && (
            <div className="absolute left-1/2 top-3 z-[4] flex -translate-x-1/2 animate-up items-center gap-2.5 rounded-[10px] border border-risk/30 bg-side/90 px-3 py-1.5 text-sm backdrop-blur">
              <b>
                {hubNameVi(selected.source_name)} → {hubNameVi(selected.target_name)}
              </b>
              <span
                className="font-mono"
                style={{ color: selected.risk_score >= 80 ? C.risk : C.warn }}
              >
                risk {selected.risk_score}
              </span>
              <span className="font-mono text-ink-soft">{usd(selected.volume_usd)}</span>
              <button
                type="button"
                onClick={() => setSelFlow(null)}
                aria-label="Bỏ chọn hành lang"
                className="text-ink-low hover:text-ink-hi"
              >
                ✕
              </button>
            </div>
          )}

          <div className="absolute bottom-2.5 left-3 z-[4] flex flex-col gap-[3px] rounded-[9px] border border-line bg-side/85 px-2.5 py-2 text-2xs text-ink-soft backdrop-blur">
            <div className="flex max-w-[300px] flex-wrap gap-2.5">
              {CHANNELS.map((ch) => (
                <span key={ch}>
                  <span style={{ color: CHANNEL[ch] }}>—</span> {CHANNEL_LABEL[ch]}
                </span>
              ))}
            </div>
            <div className="flex flex-wrap gap-2.5 border-t border-line-soft pt-1 text-ink-low">
              <span>nét đứt = bình thường</span>
              <span style={{ color: C.warnSoft }}>nét liền = đáng ngờ</span>
              <span style={{ color: C.riskSoft }}>đỏ + hạt = critical</span>
            </div>
          </div>
        </div>

        {/* --- Cột phải: inspector --- */}
        <aside className="flex min-h-0 min-w-[248px] flex-[0_4_360px] flex-col overflow-y-auto border-l border-line bg-side">
          {(selected || selectedHub) && (
            <div className="animate-up border-b border-line p-3.5">
              <div className="flex items-center gap-2">
                <span
                  className="flex-none rounded-[5px] border px-1.5 py-px font-mono text-3xs tracking-[0.06em]"
                  style={{ color: C.primary, borderColor: `${C.primary}55` }}
                >
                  {selected ? "HÀNH LANG" : "TRUNG TÂM"}
                </span>
                <div className="truncate-1 flex-1 text-xl font-semibold">
                  {selected ? `${hubNameVi(selected.source_name)} → ${hubNameVi(selected.target_name)}` : hubNameVi(selectedHub!.name)}
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setSelFlow(null);
                    setSelHub(null);
                  }}
                  aria-label="Đóng bảng thanh tra"
                  className="flex-none text-ink-low hover:text-ink-hi"
                >
                  ✕
                </button>
              </div>
              <div className="my-1 font-mono text-2xs text-ink-low">
                {selected ? `${selected.id} · ${selected.currency}` : `${selectedHub!.id} · ${selectedHub!.country}`}
              </div>

              <div className="mb-3 grid grid-cols-2 gap-[7px]">
                {(selected
                  ? [
                      { l: "Khối lượng", v: usd(selected.volume_usd), c: C.inkHi },
                      { l: "Giao dịch", v: int(selected.txn_count), c: C.inkHi },
                      {
                        l: "Điểm rủi ro",
                        v: String(selected.risk_score),
                        c: selected.risk_score >= 80 ? C.risk : C.warn,
                      },
                      { l: "Cảnh báo", v: String(selected.alert_count), c: C.risk },
                      { l: "Kênh", v: CHANNEL_LABEL[selected.channel], c: CHANNEL[selected.channel] },
                      { l: "Nhóm hành vi", v: selected.typology_hint ?? "—", c: C.inkSoft },
                    ]
                  : [
                      { l: "Khối lượng", v: usd(selectedHub!.volume_usd), c: C.inkHi },
                      { l: "Thực thể", v: int(selectedHub!.entities), c: C.inkHi },
                      { l: "Vào / Ra", v: `${selectedHub!.inbound} / ${selectedHub!.outbound}`, c: C.info },
                      { l: "Cảnh báo", v: String(selectedHub!.alerts), c: C.risk },
                      { l: "Rủi ro cao nhất", v: String(selectedHub!.risk_score), c: C.warn },
                      { l: "Rủi ro pháp lý", v: riskRatingLabel(selectedHub!.jurisdiction_risk), c: C.agent },
                    ]
                ).map((r) => (
                  <div key={r.l} className="min-w-0 rounded-[9px] bg-panel px-2.5 py-1.5">
                    <div className="truncate-1 text-3xs text-ink-low">{r.l}</div>
                    <div className="truncate-1 font-mono text-md font-semibold" style={{ color: r.c }}>
                      {r.v}
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex gap-2">
                <Link
                  to="/cases"
                  className="flex-[1.2] rounded-control border border-primary-line bg-primary-soft py-1.5 text-center text-base font-semibold text-primary transition-colors hover:bg-primary/25"
                >
                  Mở cuộc điều tra
                </Link>
                <Link
                  to="/network"
                  className="flex-1 rounded-control border border-line-strong py-1.5 text-center text-base text-ink-mid transition-colors hover:border-line-strong/60"
                >
                  Xem network
                </Link>
              </div>
            </div>
          )}

          <div className="flex items-center gap-2 px-3.5 pb-1.5 pt-3">
            <PulseDot color={C.risk} size={6} />
            <span className="text-sm font-semibold">Hành lang rủi ro cao</span>
          </div>
          <div className="flex flex-col gap-[3px] px-2.5 pb-1.5">
            {[...(world.data?.flows ?? [])]
              .filter((f) => f.risk_score >= 60)
              .sort((a, b) => b.risk_score - a.risk_score)
              .map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => {
                    setSelFlow(f.id);
                    setSelHub(null);
                  }}
                  className="flex items-center gap-2 rounded-[7px] px-1.5 py-1.5 text-left text-sm transition-colors hover:bg-elev"
                >
                  <span className="h-[7px] w-[7px] flex-none rounded-sm" style={{ background: CHANNEL[f.channel] }} />
                  <span className="truncate-1 flex-1 text-ink-mid">
                    {hubNameVi(f.source_name)} → {hubNameVi(f.target_name)}
                  </span>
                  <b
                    className="tabular flex-none font-mono text-xs"
                    style={{ color: f.risk_score >= 80 ? C.risk : C.warn }}
                  >
                    {f.risk_score}
                  </b>
                </button>
              ))}
          </div>

          <div className="flex items-center gap-2 border-t border-line-soft px-3.5 pb-1.5 pt-2">
            <span className="text-sm font-semibold">Trung tâm theo khối lượng</span>
          </div>
          <div className="flex flex-col gap-[3px] px-2.5 pb-3">
            {[...(world.data?.hubs ?? [])]
              .sort((a, b) => b.volume_usd - a.volume_usd)
              .map((h) => (
                <button
                  key={h.id}
                  type="button"
                  onClick={() => {
                    setSelHub(h.id);
                    setSelFlow(null);
                  }}
                  className="flex items-center gap-2 rounded-[7px] px-1.5 py-1.5 text-left text-sm transition-colors hover:bg-elev"
                >
                  <span className="truncate-1 flex-1 text-ink-mid">{hubNameVi(h.name)}</span>
                  <span className="tabular flex-none font-mono text-2xs text-ink-low">{usd(h.volume_usd)}</span>
                </button>
              ))}
          </div>
        </aside>
      </div>

      {/* --- Dải phân tích dưới cùng --- */}
      <div
        className="flex flex-none flex-col overflow-hidden border-t border-line bg-side transition-[height] duration-200"
        style={{ height: bottomOpen ? 172 : 45 }}
      >
        <div className="flex items-center gap-2.5 border-b border-line-soft px-3.5 py-2">
          <button
            type="button"
            onClick={() => setPaused((v) => !v)}
            aria-label={paused ? "Chạy tiếp" : "Tạm dừng"}
            className="grid h-7 w-7 place-items-center rounded-control border border-primary-line bg-primary-soft text-primary transition-colors hover:bg-primary/25"
          >
            {paused ? <Play size={11} /> : <Pause size={11} />}
          </button>
          <div className="flex gap-0.5 rounded-control border border-line bg-sunken p-0.5">
            {SPEEDS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSpeed(s)}
                className={`rounded-[6px] px-2 py-[3px] font-mono text-xs transition-colors ${
                  speed === s ? "bg-primary-soft text-primary" : "text-ink-soft hover:text-ink-hi"
                }`}
              >
                {s}×
              </button>
            ))}
          </div>
          <input
            type="range"
            min={0}
            max={100}
            step={0.5}
            value={replayT}
            onChange={(e) => setReplayT(Number(e.target.value))}
            aria-label="Thanh trượt thời gian"
            className="min-w-[120px] flex-1 accent-info"
          />
          <span className="tabular w-[92px] flex-none text-right font-mono text-2xs text-ink-soft">
            {replayT >= 100 ? "thời gian thực" : `phát lại ${replayT.toFixed(0)}%`}
          </span>
          <button
            type="button"
            onClick={() => setBottomOpen((v) => !v)}
            aria-label={bottomOpen ? "Thu gọn dải phân tích" : "Mở dải phân tích"}
            className="grid h-[26px] w-7 place-items-center rounded-control border border-line-strong/70 text-ink-soft transition-colors hover:text-ink-hi"
          >
            <Maximize2 size={11} />
          </button>
        </div>

        {bottomOpen && (
          <div className="flex min-h-0 flex-1 overflow-x-auto">
            <div className="min-w-[190px] flex-[1.3_1_210px] px-2 pt-2">
              <div className="px-2 pb-0.5 text-2xs text-ink-low">Cơ cấu theo kênh (triệu USD)</div>
              <Chart spec={channelMixSpec} height={108} />
            </div>
            <div className="min-w-[225px] flex-[1.2_1_230px] border-l border-line-soft px-2 pt-2">
              <div className="px-1 pb-0.5 text-2xs text-ink-low">Xếp hạng hành lang (triệu USD)</div>
              <Chart spec={corridorRankSpec} height={108} />
            </div>
            <div className="min-w-[190px] flex-[1.3_1_210px] border-l border-line-soft px-2 pt-2">
              <div className="px-1 pb-0.5 text-2xs text-ink-low">Rủi ro cao nhất theo kênh</div>
              <Chart spec={riskByChannelSpec} height={108} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
