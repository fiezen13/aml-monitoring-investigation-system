import { Database, MapPinOff, Maximize2, Pause, Play } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { int } from "../api/fcFormat";
import { riskRatingLabel } from "../api/format";
import { useApi } from "../api/useApi";
import { Chart, type ChartSpec } from "../components/fc/Chart";
import { WorldMap, type MapData } from "../components/fc/WorldMap";
import {
  Badge,
  Button,
  Eyebrow,
  IconButton,
  Inspector,
  Panel,
  PageShell,
  PulseDot,
  SegmentedControl,
  StatTile,
  Switch,
} from "../components/ui";
import { mapSurface } from "../design/adapters/mapTheme";
import { CHANNEL, CHANNEL_LABEL, getRiskTone, severityOf, toneColor, type Tone } from "../design";

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

function nativeAmount(value: number, currency: string): string {
  return `${value.toLocaleString("vi-VN", { maximumFractionDigits: 8 })} ${currency}`;
}

export function WorldPage() {
  const world = useApi(() => api.world(), []);

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
  // Mặc định đóng dải phân tích. Ba biểu đồ dưới đáy đọc cùng bộ dữ liệu mà bản
  // đồ đã thể hiện, nhưng chúng chiếm 172px chiều cao — đúng phần khiến bản đồ
  // bị bó lại. Người cần vẫn mở được bằng nút ở góc phải dải.
  const [bottomOpen, setBottomOpen] = useState(false);

  // Nhãn ngắn cho huy hiệu góc bản đồ. "IBM AML LI-Small currency-native" quá
  // dài cho một dòng chip, nhưng phần "IBM AML" thì mọi màn hình đều đã nói rồi.
  const datasetBadge = (world.data?.source_name ?? "")
    .replace(/^IBM AML\s*/i, "")
    .toUpperCase()
    .trim() || "CHƯA XÁC ĐỊNH";
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
        // Kích thước chấm theo số giao dịch vào/ra, không cộng amount của
        // nhiều currency thành một đại lượng giả.
        size: Math.max(1.2, Math.min(3, Math.log10(Math.max(10, h.inbound + h.outbound)) / 2.5)),
        vol: `${int(h.inbound + h.outbound)} giao dịch`,
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
        vol: nativeAmount(f.amount_native, f.currency),
        // Engine chỉ dùng trường này để xếp hạng/độ dày cung. Dùng số giao
        // dịch vì không được cộng khối lượng của nhiều currency.
        volUsd: f.txn_count,
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
    const total = flows.reduce((s, f) => s + f.txn_count, 0);
    const susp = flows.filter((f) => f.risk_score >= 60);
    const crit = flows.filter((f) => f.risk_score >= 80);
    return [
      { l: "Giao dịch xuyên biên giới", v: int(total), t: "neutral" as Tone, d: `${flows.length} hành lang/currency` },
      {
        l: "Đáng ngờ",
        v: int(susp.reduce((sum, f) => sum + f.txn_count, 0)),
        t: "warn" as Tone,
        d: `${susp.length} hành lang`,
      },
      { l: "Nghiêm trọng", v: String(crit.length), t: "risk" as Tone, d: "cần xử lý ngay" },
      { l: "Giao dịch", v: int(flows.reduce((sum, f) => sum + f.txn_count, 0)), t: "neutral" as Tone, d: "trong cửa sổ" },
      // Cộng dồn alert_count qua các hành lang là ĐẾM TRÙNG: một cảnh báo chạm
      // nhiều hành lang thì được cộng nhiều lần. Số đo đúng cho một tấm thẻ là
      // cao nhất trên một hành lang, không phải tổng — 5.004 cảnh báo thật từng
      // hiện thành 19.258 vì phép cộng này.
      {
        l: "Cảnh báo",
        v: String(flows.reduce((peak, f) => Math.max(peak, f.alert_count), 0)),
        t: "risk" as Tone,
        d: "trên hành lang nặng nhất",
      },
      { l: "Trung tâm", v: String(world.data?.hubs.length ?? 0), t: "info" as Tone, d: "đang theo dõi" },
    ];
  }, [world.data]);

  const selected = world.data?.flows.find((f) => f.id === selFlow) ?? null;
  const selectedHub = world.data?.hubs.find((h) => h.id === selHub) ?? null;

  // --- các biểu đồ ở dải dưới ---

  const channelMixSpec = useMemo<ChartSpec | null>(() => {
    const flows = world.data?.flows;
    if (!flows?.length) return null;
    const byCh = new Map<string, number>();
    for (const f of flows) byCh.set(f.channel, (byCh.get(f.channel) ?? 0) + f.txn_count);
    return {
      type: "donut",
      items: [...byCh.entries()].map(([ch, v]) => ({
        label: CHANNEL_LABEL[ch] ?? ch,
        value: v,
        color: CHANNEL[ch],
      })),
    };
  }, [world.data]);

  const corridorRankSpec = useMemo<ChartSpec | null>(() => {
    const flows = world.data?.flows;
    if (!flows?.length) return null;
    const top = [...flows].sort((a, b) => b.txn_count - a.txn_count).slice(0, 8);
    return {
      type: "hbars",
      items: top.map((f) => ({
        label: `${hubNameVi(f.source_name).slice(0, 12)} → ${hubNameVi(f.target_name).slice(0, 12)}`,
        value: f.txn_count,
        color: toneColor(f.risk_score >= 80 ? "risk" : f.risk_score >= 60 ? "warn" : "info"),
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
          color: toneColor("warn"),
        },
      ],
    };
  }, [world.data]);

  if (!world.loading && world.data?.data_mode === "operational" && !world.data.geography_available) {
    return (
      <PageShell
        title="Không đủ dữ liệu để dựng bản đồ địa lý"
        subtitle="Hệ thống không suy diễn quốc gia hoặc toạ độ từ mã ngân hàng. Bản đồ được chủ động tắt thay vì ghép lô dữ liệu IBM với kịch bản Việt Nam không liên quan."
        actions={
          <Badge tone="warn" icon={<MapPinOff size={12} aria-hidden />}>
            Chưa có dữ liệu địa lý đã kiểm chứng
          </Badge>
        }
      >
        <div className="grid gap-3.5 md:grid-cols-3">
          <Panel
            title={
              <span className="flex items-center gap-2">
                <Database size={15} className="text-primary" aria-hidden /> Nguồn đang hoạt động
              </span>
            }
            className="md:col-span-2"
          >
            <dl className="grid gap-3 text-body sm:grid-cols-2">
              <div>
                <dt className="text-meta text-ink-low">Tệp nguồn</dt>
                <dd className="mt-1 font-mono text-ink-mid">{world.data.source_name ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-meta text-ink-low">Mã lô dữ liệu</dt>
                <dd className="mt-1 font-mono text-ink-mid">{world.data.source_id ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-meta text-ink-low">Giao dịch đã chấm điểm</dt>
                <dd className="mt-1 font-mono text-h3 font-semibold text-ink-hi">
                  {int(world.data.transaction_count)}
                </dd>
              </div>
              <div>
                <dt className="text-meta text-ink-low">Phạm vi địa lý</dt>
                <dd className="mt-1 font-medium text-warn-soft">Không được cung cấp</dd>
              </div>
            </dl>
          </Panel>

          <Panel title="Giới hạn dữ liệu">
            <p className="text-meta leading-relaxed text-ink-soft">{world.data.limitation}</p>
            <p className="mt-3 text-meta leading-relaxed text-ink-low">
              Mã ngân hàng trong IBM AML là mã định danh của tập dữ liệu, không phải mã quốc gia và không đủ để đặt
              một điểm lên bản đồ.
            </p>
          </Panel>
        </div>

        <Panel
          title="Dữ liệu giao dịch vẫn xem được đầy đủ"
          subtitle="Tra cứu giao dịch đọc trực tiếp bảng giao dịch và gồm cả giao dịch dưới ngưỡng ML hành vi."
          actions={
            <Link to="/transactions">
              <Button size="sm">Mở Tra cứu giao dịch</Button>
            </Link>
          }
        >
          <Eyebrow>Giám sát địa lý · dữ liệu vận hành</Eyebrow>
        </Panel>
      </PageShell>
    );
  }

  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden">
      {/* Dưới 1024px ba cột xếp chồng: giữ nguyên lưới cố định ở đó nghĩa là
          bản đồ chỉ còn khoảng 400px giữa hai cột panel. */}
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-x-auto lg:overflow-y-hidden">
        {/* --- Cột trái: bộ lọc --- */}
        <aside className="flex flex-none flex-col gap-3.5 border-b border-line bg-side p-3.5 lg:min-w-[216px] lg:flex-[0_3_300px] lg:overflow-y-auto lg:border-b-0 lg:border-r">
          <div className="rounded-[9px] border border-line bg-panel p-2.5">
            {/* Tên bộ dữ liệu đọc từ payload, không viết cứng: trang này từng
                ghi "HI-Medium" trong khi máy chủ phục vụ LI-Small. */}
            <div className="text-3xs font-semibold uppercase tracking-[0.09em] text-ink-dim">
              Dữ liệu {world.data?.source_name ?? "chưa xác định"}
            </div>
            <p className="mt-1 text-2xs leading-relaxed text-ink-soft">{world.data?.limitation}</p>
          </div>
          <div>
            <Eyebrow className="mb-2">Chỉ số release đang hoạt động</Eyebrow>
            <div className="grid grid-cols-2 gap-[7px]">
              {stats.map((stat) => (
                <StatTile key={stat.l} label={stat.l} value={stat.v} sub={stat.d} tone={stat.t} />
              ))}
            </div>
          </div>

          <div>
            <Eyebrow className="mb-2">Các lớp dòng tiền</Eyebrow>
            <div className="flex flex-col gap-1">
              {CHANNELS.map((ch) => (
                <div key={ch} className="flex items-center gap-2.5 rounded-control px-2 py-1.5 text-body">
                  <span className="h-[9px] w-[9px] flex-none rounded-sm" style={{ background: CHANNEL[ch] }} aria-hidden />
                  <span className="flex-1 text-left text-ink-mid">{CHANNEL_LABEL[ch]}</span>
                  {/* Công tắc mang màu của chính lớp đó, không phải màu accent
                      chung: sáu công tắc cùng một sắc teal thì chỉ nói được
                      "đang bật", còn ở đây chúng nói luôn "đang bật cái gì". */}
                  <Switch
                    size="sm"
                    checked={layers[ch]}
                    color={CHANNEL[ch]}
                    label={`Lớp ${CHANNEL_LABEL[ch]}`}
                    onChange={(next) => setLayers((current) => ({ ...current, [ch]: next }))}
                  />
                </div>
              ))}
            </div>
          </div>

          <div>
            <Eyebrow className="mb-2">Mức độ</Eyebrow>
            <SegmentedControl
              label="Mức độ hành lang"
              size="sm"
              className="w-full"
              value={sev}
              onChange={setSev}
              options={SEVERITIES.map((item) => ({ value: item.key, label: item.label }))}
            />
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
            bảng thanh tra · nháy đúp nền để đặt lại. Đây là rollup từ giao dịch{" "}
            {world.data?.source_name ?? "đã nạp"} đã được model chấm.
          </p>
        </aside>

        {/* --- Cột giữa: bản đồ --- */}
        {/* Nền dưới bản đồ dùng chính bảng màu bề mặt bản đồ, nên khoảnh khắc
            trước khi bộ dựng hình vẽ xong không loé lên một tông khác. */}
        <div
          className="relative h-[420px] flex-none overflow-hidden lg:h-auto lg:min-w-[390px] lg:flex-[1_1_480px]"
          style={{
            background: `radial-gradient(ellipse at 50% 42%, ${mapSurface.land} 0%, ${mapSurface.space} 72%)`,
          }}
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

          <div className="absolute left-3.5 top-3 z-hud flex items-center gap-2 rounded-chip border border-line-strong bg-raised/85 px-3 py-1 text-meta backdrop-blur">
            <PulseDot tone={world.error ? "risk" : "ok"} />
            <span className={`font-mono tracking-[0.08em] ${world.error ? "text-risk-soft" : "text-ok-soft"}`}>
              {world.error ? "MẤT KẾT NỐI" : world.loading ? "ĐANG TẢI" : datasetBadge}
            </span>
          </div>

          {/* Bộ chọn phép chiếu. Chỉ báo trượt giữa hai lựa chọn thay vì mỗi
              nút tự bật nền của mình — cùng ngôn ngữ với tab và cửa sổ thời
              gian ở header, và nó nói rằng đây là một trục chứ không phải hai
              chế độ rời rạc. */}
          <div className="absolute right-3 top-2.5 z-hud flex items-center gap-1.5">
            <SegmentedControl
              label="Phép chiếu bản đồ"
              size="sm"
              value={mode}
              onChange={setMode}
              options={[
                { value: "map", label: "Bản đồ" },
                { value: "globe", label: "Quả cầu" },
              ]}
              className="bg-raised/85 backdrop-blur"
            />
            <SegmentedControl
              label="Số hành lang hiển thị"
              size="sm"
              value={String(topN)}
              onChange={(value) => setTopN(Number(value))}
              options={TOP_N.map((n) => ({ value: String(n), label: `Top ${n}` }))}
              className="bg-raised/85 backdrop-blur"
            />
            <Button
              size="sm"
              variant={hideNormal ? "primary" : "secondary"}
              onClick={() => setHideNormal((value) => !value)}
              title="Chỉ hiện dòng tiền đáng ngờ"
              className={hideNormal ? "" : "bg-raised/85 backdrop-blur"}
            >
              Chỉ đáng ngờ
            </Button>
          </div>

          {selected && (
            <div className="absolute left-1/2 top-3 z-hud flex -translate-x-1/2 animate-up items-center gap-2.5 rounded-panel border border-line-strong bg-raised/90 px-3 py-1.5 text-data backdrop-blur">
              <b className="text-ink-hi">
                {hubNameVi(selected.source_name)} → {hubNameVi(selected.target_name)}
              </b>
              <Badge tone={getRiskTone(selected.risk_score)} icon={false} className="font-mono">
                rủi ro {selected.risk_score}
              </Badge>
              <span className="font-mono text-ink-soft">{nativeAmount(selected.amount_native, selected.currency)}</span>
              <IconButton size="sm" label="Bỏ chọn hành lang" icon={<span aria-hidden>✕</span>} onClick={() => setSelFlow(null)} />
            </div>
          )}

          <div className="absolute bottom-2.5 left-3 z-hud flex flex-col gap-[3px] rounded-control border border-line-strong bg-raised/85 px-2.5 py-2 text-meta text-ink-soft backdrop-blur">
            <div className="flex max-w-[300px] flex-wrap gap-2.5">
              {CHANNELS.map((ch) => (
                <span key={ch}>
                  <span style={{ color: CHANNEL[ch] }}>—</span> {CHANNEL_LABEL[ch]}
                </span>
              ))}
            </div>
            <div className="flex flex-wrap gap-2.5 border-t border-line-soft pt-1 text-ink-low">
              <span>nét đứt = bình thường</span>
              <span className="text-warn-soft">nét liền = đáng ngờ</span>
              <span className="text-risk-soft">đỏ + hạt = nghiêm trọng</span>
            </div>
          </div>
        </div>

        {/* --- Cột phải: inspector --- */}
        <aside className="flex min-h-0 flex-none flex-col border-t border-line bg-side lg:min-w-[248px] lg:flex-[0_4_360px] lg:overflow-y-auto lg:border-l lg:border-t-0">
          {/* Bảng thanh tra sống độc lập với bộ dựng hình: đổi 2D↔3D không đụng
              tới nó, còn đổi thực thể đang xem thì nội dung trượt vào lại. */}
          {(selected || selectedHub) && (
            <Inspector animateKey={selected?.id ?? selectedHub?.id ?? null} className="border-b border-line p-3.5">
              <div className="flex items-center gap-2">
                <Badge tone="primary" icon={false} variant="outline" className="font-mono tracking-[0.06em]">
                  {selected ? "HÀNH LANG" : "TRUNG TÂM"}
                </Badge>
                <div className="truncate-1 flex-1 text-h3 font-semibold text-ink-hi">
                  {selected
                    ? `${hubNameVi(selected.source_name)} → ${hubNameVi(selected.target_name)}`
                    : hubNameVi(selectedHub!.name)}
                </div>
                <IconButton
                  size="sm"
                  label="Đóng bảng thanh tra"
                  icon={<span aria-hidden>✕</span>}
                  onClick={() => {
                    setSelFlow(null);
                    setSelHub(null);
                  }}
                />
              </div>
              <div className="my-1 font-mono text-meta text-ink-low">
                {selected ? `${selected.id} · ${selected.currency}` : `${selectedHub!.id} · ${selectedHub!.country}`}
              </div>

              <div className="mb-3 grid grid-cols-2 gap-[7px]">
                {(selected
                  ? [
                      { l: "Giá trị gốc", v: nativeAmount(selected.amount_native, selected.currency), t: "neutral" as Tone },
                      { l: "Giao dịch", v: int(selected.txn_count), t: "neutral" as Tone },
                      { l: "Điểm rủi ro", v: String(selected.risk_score), t: getRiskTone(selected.risk_score) },
                      { l: "Cảnh báo", v: String(selected.alert_count), t: "risk" as Tone },
                      { l: "Kênh", v: CHANNEL_LABEL[selected.channel], t: "info" as Tone },
                      { l: "Nhóm hành vi", v: selected.typology_hint ?? "—", t: "neutral" as Tone },
                    ]
                  : [
                      { l: "Hoạt động", v: int(selectedHub!.inbound + selectedHub!.outbound), t: "neutral" as Tone },
                      { l: "Thực thể", v: int(selectedHub!.entities), t: "neutral" as Tone },
                      { l: "Vào / Ra", v: `${selectedHub!.inbound} / ${selectedHub!.outbound}`, t: "info" as Tone },
                      { l: "Cảnh báo", v: String(selectedHub!.alerts), t: "risk" as Tone },
                      { l: "Rủi ro cao nhất", v: String(selectedHub!.risk_score), t: getRiskTone(selectedHub!.risk_score) },
                      {
                        l: "Rủi ro pháp lý",
                        v: riskRatingLabel(selectedHub!.jurisdiction_risk),
                        t: "agent" as Tone,
                      },
                    ]
                ).map((row) => (
                  <StatTile key={row.l} label={row.l} value={row.v} tone={row.t} />
                ))}
              </div>

              <div className="flex gap-2">
                <Link
                  to="/cases"
                  className="flex-[1.2] rounded-control border border-primary/30 bg-primary-soft py-1.5 text-center text-body font-semibold text-primary transition-colors hover:bg-primary/20"
                >
                  Mở cuộc điều tra
                </Link>
                <Link
                  to="/network"
                  className="flex-1 rounded-control border border-line-strong py-1.5 text-center text-body text-ink-mid transition-colors hover:border-line-emphasis hover:text-ink-hi"
                >
                  Xem đồ thị mạng lưới
                </Link>
              </div>
            </Inspector>
          )}

          <div className="flex items-center gap-2 px-3.5 pb-1.5 pt-3">
            <PulseDot tone="risk" size={6} />
            <span className="text-body font-semibold text-ink-hi">Hành lang rủi ro cao</span>
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
                  <b className={`tabular flex-none font-mono text-data ${
                    f.risk_score >= 80 ? "text-risk-soft" : "text-warn-soft"
                  }`}>
                    {f.risk_score}
                  </b>
                </button>
              ))}
          </div>

          <div className="flex items-center gap-2 border-t border-line-soft px-3.5 pb-1.5 pt-2">
            <span className="text-body font-semibold text-ink-hi">Trung tâm theo hoạt động</span>
          </div>
          <div className="flex flex-col gap-[3px] px-2.5 pb-3">
            {[...(world.data?.hubs ?? [])]
              .sort((a, b) => b.inbound + b.outbound - (a.inbound + a.outbound))
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
                  {/* inbound + outbound là số LƯỢT chạm quốc gia, không phải số giao dịch:
                        một giao dịch nội địa tính cả chiều đi lẫn chiều đến. */}
                    <span className="tabular flex-none font-mono text-2xs text-ink-low">
                      {int(h.inbound + h.outbound)} lượt
                    </span>
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
          <IconButton
            size="sm"
            active
            label={paused ? "Chạy tiếp" : "Tạm dừng"}
            icon={paused ? <Play size={11} /> : <Pause size={11} />}
            onClick={() => setPaused((value) => !value)}
          />
          <SegmentedControl
            label="Tốc độ phát lại"
            size="sm"
            value={String(speed)}
            onChange={(value) => setSpeed(Number(value))}
            options={SPEEDS.map((value) => ({ value: String(value), label: `${value}×` }))}
          />
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
          <span className="tabular w-[92px] flex-none text-right font-mono text-meta text-ink-soft">
            {replayT >= 100 ? "thời gian thực" : `phát lại ${replayT.toFixed(0)}%`}
          </span>
          <IconButton
            size="sm"
            variant="secondary"
            label={bottomOpen ? "Thu gọn dải phân tích" : "Mở dải phân tích"}
            icon={<Maximize2 size={11} />}
            onClick={() => setBottomOpen((value) => !value)}
          />
        </div>

        {bottomOpen && (
          <div className="flex min-h-0 flex-1 overflow-x-auto">
            <div className="min-w-[190px] flex-[1.3_1_210px] px-2 pt-2">
              <div className="px-2 pb-0.5 text-meta text-ink-low">Cơ cấu theo kênh (số giao dịch)</div>
              <Chart spec={channelMixSpec} height={108} />
            </div>
            <div className="min-w-[225px] flex-[1.2_1_230px] border-l border-line-soft px-2 pt-2">
              <div className="px-1 pb-0.5 text-meta text-ink-low">Xếp hạng hành lang (số giao dịch)</div>
              <Chart spec={corridorRankSpec} height={108} />
            </div>
            <div className="min-w-[190px] flex-[1.3_1_210px] border-l border-line-soft px-2 pt-2">
              <div className="px-1 pb-0.5 text-meta text-ink-low">Rủi ro cao nhất theo kênh</div>
              <Chart spec={riskByChannelSpec} height={108} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
