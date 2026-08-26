/** Nhãn tiếng Việt cho nhóm hành vi và tín hiệu.
 *
 * Danh mục `src/investigation/typologies.json` viết bằng tiếng Anh vì nó là hợp
 * đồng dữ liệu — mã `T02`, tên tín hiệu `network_flow` được tác tử và bộ phản
 * biện đối chiếu, đổi chúng là phá hợp đồng.
 *
 * Nhưng màn hình là tiếng Việt, và một chuyên viên tuân thủ đọc
 * "T02 — Intermediary account network" hay "chưa kiểm tra được network_flow,
 * rapid_outflow" thì không hiểu gì. Bảng này chỉ dịch phần HIỂN THỊ; dữ liệu bên
 * dưới giữ nguyên mã gốc để vẫn truy vết được.
 */

export const TYPOLOGY_LABELS: Record<string, { name: string; description: string }> = {
  T01: {
    name: "Chia nhỏ giao dịch dưới ngưỡng báo cáo",
    description: "Nhiều giao dịch lặp lại ngay dưới ngưỡng phải báo cáo, cần rà theo ngữ cảnh.",
  },
  T02: {
    name: "Mạng lưới tài khoản trung chuyển",
    description: "Tiền đi qua các tài khoản trung gian để dồn về một điểm gom hoặc chuyển tiếp ra ngoài.",
  },
  T03: {
    name: "Dòng tiền khép vòng",
    description: "Tiền đi một vòng qua nhiều tài khoản rồi quay lại chính tài khoản xuất phát.",
  },
  T04: {
    name: "Gom vào rồi toả ra bất thường",
    description: "Nhiều nguồn dồn tiền về một tài khoản, sau đó phân tán ra nhiều đích.",
  },
  T05: {
    name: "Luân chuyển tiền tốc độ cao",
    description: "Tiền vừa vào đã rời tài khoản trong thời gian rất ngắn.",
  },
  T06: {
    name: "Liên quan vùng tài phán rủi ro cao",
    description: "Giao dịch dính tới một vùng tài phán bị xếp mức rủi ro cao theo chính sách.",
  },
  T07: {
    name: "Lệch hồ sơ khách hàng",
    description: "Hành vi giao dịch khác hẳn hồ sơ và mức hoạt động đã khai báo.",
  },
  // T08 đã gỡ: luật VASP (R03_VASP_EXPOSURE) — nguồn duy nhất sinh T08 — dựa
  // trên cờ is_vasp do dự án tự gán nên đã bỏ; không detector nào còn phát T08.
  T09: {
    name: "Lệch giá trị trong thương mại",
    description: "Giá trị khai trong chứng từ thương mại lệch so với dòng tiền thực tế.",
  },
  T10: {
    name: "Liên quan tài sản mã hoá",
    description: "Dòng tiền đi qua điểm chuyển đổi vào hoặc ra tài sản mã hoá.",
  },
};

export const SIGNAL_LABELS: Record<string, string> = {
  rule_trigger: "luật nghiệp vụ kích hoạt",
  repeated_amounts: "số tiền lặp lại",
  short_window: "dồn trong thời gian ngắn",
  network_flow: "tiền đi qua tài khoản trung gian",
  rapid_outflow: "tiền ra ngay sau khi nhận",
  new_counterparties: "đối tác mới xuất hiện",
  directed_cycle: "vòng tiền khép kín",
  short_duration: "vòng khép trong thời gian ngắn",
  value_retention: "giữ lại một phần giá trị sau mỗi vòng",
  fan_in: "nhiều nguồn dồn vào",
  fan_out: "phân tán ra nhiều đích",
  short_dwell_time: "tiền nằm lại rất ngắn",
  jurisdiction_signal: "dấu hiệu vùng tài phán",
  cross_border_flow: "dòng tiền xuyên biên giới",
  profile_deviation: "lệch hồ sơ khách hàng",
  volume_deviation: "lệch mức hoạt động thường thấy",
  shared_device: "dùng chung thiết bị",
  identity_mismatch: "thông tin định danh không khớp",
  trade_value_mismatch: "lệch giá trị chứng từ thương mại",
  repeated_counterparty: "lặp lại cùng một đối tác",
  vasp_link: "liên hệ với sàn tài sản mã hoá",
  rapid_cross_channel_flow: "chuyển nhanh qua nhiều kênh",
};

/** Tên nhóm để hiển thị. Giữ mã gốc phía trước để vẫn đối chiếu được. */
export function typologyLabel(code: string, fallbackName?: string): string {
  const vi = TYPOLOGY_LABELS[code];
  return vi ? `${code} — ${vi.name}` : `${code}${fallbackName ? ` — ${fallbackName}` : ""}`;
}

export function typologyDescription(code: string, fallback?: string): string {
  return TYPOLOGY_LABELS[code]?.description ?? fallback ?? "";
}

/** Tín hiệu chưa có bản dịch vẫn hiện ra dưới tên gốc — giấu đi là giấu bằng chứng. */
export function signalLabel(signal: string): string {
  return SIGNAL_LABELS[signal] ?? signal;
}

export function signalList(signals: string[]): string {
  return signals.map(signalLabel).join(", ");
}
