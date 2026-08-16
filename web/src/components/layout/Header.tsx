import { Bell, Menu, Search } from "lucide-react";
import { useState } from "react";

import { useApp } from "../../context/AppContext";
import { useConsole } from "../../context/ConsoleContext";
import { TEXT } from "../../design/typography";
import { Badge, IconButton, Popover, PulseDot, Select } from "../ui";

interface Props {
  /** Tên màn hình hiện tại. Đây là chỗ DUY NHẤT hiển thị nó. */
  crumb?: string;
  /** Số cảnh báo mức nghiêm trọng, hiện ở chuông thông báo. */
  criticalCount?: number;
  /** Chỉ có ở khung hẹp, nơi sidebar là lớp phủ. */
  onOpenNav?: () => void;
  /** Kỳ dữ liệu đang hiển thị, lấy từ `/nav-counts`. */
  dataPeriod?: { start: string | null; end: string | null };
}

const WORLDS = ["FIN-07 Chính", "FIN-07 Mô phỏng sức chịu đựng"];
/** `2022-09-01` → `01/09/2022`. Giữ nguyên chuỗi ISO nếu định dạng lạ. */
function viDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const [y, m, d] = iso.split("-");
  return y && m && d ? `${d}/${m}/${y}` : iso;
}

export function Header({ crumb, criticalCount = 0, onOpenNav, dataPeriod }: Props) {
  const { currentUser } = useApp();
  const { world, setWorld, setPaletteOpen } = useConsole();
  const [bellOpen, setBellOpen] = useState(false);

  const start = viDate(dataPeriod?.start);
  const end = viDate(dataPeriod?.end);
  const periodLabel = start && end ? `${start} – ${end}` : null;

  const initials = (currentUser?.name ?? "")
    .split(" ")
    .slice(-2)
    .map((word) => word[0])
    .join("");

  return (
    <header className="flex h-14 flex-none items-center gap-2 border-b border-line-soft bg-side px-3 lg:px-4">
      {onOpenNav && (
        <IconButton label="Mở thanh điều hướng" icon={<Menu size={17} />} onClick={onOpenNav} size="sm" />
      )}

      <h1 className={`truncate-1 flex-none ${TEXT.h3}`}>{crumb}</h1>

      <button
        type="button"
        onClick={() => setPaletteOpen(true)}
        className="ml-1 flex h-8 min-w-0 flex-[0_1_300px] items-center gap-2 overflow-hidden rounded-control border border-line-strong bg-sunken px-2.5 text-ink-low transition-colors hover:border-line-emphasis hover:text-ink-mid"
      >
        <Search size={13} className="flex-none" aria-hidden />
        <span className="truncate-1 flex-1 text-left text-data">Tìm thực thể, vụ việc, cảnh báo…</span>
        <span className="hidden flex-none rounded-sm border border-line-strong px-1.5 font-mono text-micro sm:block">
          ⌘K
        </span>
      </button>

      <div className="flex-1" />

      {/* Môi trường mô phỏng lùi xuống dưới 1280px: nó đổi rất hiếm, còn cửa sổ
          thời gian thì analyst chạm liên tục. */}
      <Select
        aria-label="Thế giới mô phỏng"
        value={world}
        onChange={(event) => setWorld(event.target.value)}
        className="hidden w-[210px] xl:block"
      >
        {WORLDS.map((name) => (
          <option key={name} value={name}>
            Môi trường: {name}
          </option>
        ))}
      </Select>

      {/* Đây từng là bộ chọn 1h/24h/7d/30d. Nó không nối vào truy vấn nào —
          `/dashboard` chỉ trả tổng của một lô chạy, không có trường nào theo
          trục thời gian — nên bấm vào không có gì đổi ngoài một dòng nhãn.
          Tệ hơn: nối thật cũng vô nghĩa, vì cảnh báo chỉ được tạo ở ba mốc và
          mốc gần nhất đã cách hiện tại hơn một ngày, nên "1h" và "24h" sẽ luôn
          trả về rỗng.

          Thay bằng câu trả lời thật cho đúng câu hỏi mà bộ chọn ấy gợi ra:
          người dùng đang nhìn khoảng thời gian nào. */}
      {periodLabel && (
        <Badge
          tone="neutral"
          icon={false}
          className="hidden whitespace-nowrap sm:inline-flex"
          title="Toàn bộ số liệu trên console tính trên đúng khoảng thời gian này"
        >
          Dữ liệu {periodLabel}
        </Badge>
      )}

      {/* Nhãn này không phải trang trí: toàn bộ dữ liệu trong console là tổng
          hợp, và người xem phải biết điều đó ở mọi màn hình. */}
      <Badge tone="warn" icon={false} className="font-mono tracking-[0.08em]" title="Bản trình diễn khái niệm">
        POC
      </Badge>

      <div
        title="Trạng thái luồng dữ liệu"
        className="hidden items-center gap-1.5 whitespace-nowrap text-meta text-ink-soft lg:flex"
      >
        <PulseDot />
        Đang hoạt động
      </div>

      <Popover
        open={bellOpen}
        onClose={() => setBellOpen(false)}
        align="right"
        width={288}
        trigger={
          <button
            type="button"
            onClick={() => setBellOpen((open) => !open)}
            aria-label={`Thông báo${criticalCount > 0 ? ` — ${criticalCount} cảnh báo nghiêm trọng` : ""}`}
            aria-expanded={bellOpen}
            className="relative grid h-8 w-8 place-items-center rounded-control text-ink-soft transition-colors hover:bg-elev hover:text-ink-hi"
          >
            <Bell size={17} strokeWidth={1.8} />
            {criticalCount > 0 && (
              <span
                className="absolute right-1.5 top-1.5 h-[7px] w-[7px] rounded-full border-[1.5px] border-side bg-risk"
                aria-hidden
              />
            )}
          </button>
        }
      >
        <div className={`${TEXT.eyebrow} mb-2`}>Thông báo nội bộ</div>
        <p className="text-meta leading-relaxed text-ink-mid">
          {criticalCount} cảnh báo đang ở mức nghiêm trọng{periodLabel ? ` trong kỳ dữ liệu ${periodLabel}` : ""}.
          Thông báo chỉ phát trong nội bộ — hệ thống không có kênh nào gửi tới chủ thể đang bị rà soát.
        </p>
      </Popover>

      <div
        title={`${currentUser?.name} · ${currentUser?.roleLabel}`}
        className="grid h-[30px] w-[30px] flex-none place-items-center rounded-full border border-line-strong bg-elev text-meta font-semibold text-ink-mid"
      >
        {initials}
      </div>
    </header>
  );
}
