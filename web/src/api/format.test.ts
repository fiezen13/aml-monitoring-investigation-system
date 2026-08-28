import { describe, expect, it } from "vitest";

import {
  evidenceSourceLabel,
  evidenceSummary,
  evidenceTitle,
  evidenceTypeLabel,
  formatAmountText,
  auditEventLabel,
  actorLabel,
  paymentChannelLabel,
  profileValueLabel,
  investigationTextVi,
  formatMoney,
} from "./format";

describe("định dạng bằng chứng cho chuyên viên", () => {
  it("không hiển thị tên dịch vụ kỹ thuật ở nguồn dữ liệu", () => {
    expect(evidenceSourceLabel("typology_registry")).toBe("Danh mục nhóm hành vi");
    expect(evidenceSourceLabel("feature_service")).toBe("Hệ thống phân tích hành vi");
    expect(evidenceSourceLabel("transaction_service")).toBe("Kho dữ liệu giao dịch");
  });

  it("dùng tên bằng chứng theo ngôn ngữ nghiệp vụ", () => {
    expect(evidenceTypeLabel("RULE_TRIGGER")).toBe("Quy tắc cảnh báo đã kích hoạt");
    expect(evidenceTypeLabel("TYPOLOGY_MAPPING")).toBe("Nhóm hành vi được đối chiếu");
    expect(evidenceTitle(undefined, "rule_engine")).toBe("Quy tắc cảnh báo đã kích hoạt");
  });

  it("tóm tắt cửa sổ hành vi thay vì hiện chuỗi tham chiếu dài", () => {
    expect(evidenceSummary("BEHAVIOR_FEATURE", { window: "30d" })).toBe(
      "Số liệu hành vi của tài khoản trong 30 ngày.",
    );
  });

  it("tóm tắt số giao dịch và nhóm hành vi", () => {
    expect(evidenceSummary("TRANSACTION", { items: [{}, {}, {}] })).toBe(
      "3 giao dịch được dùng để đối chiếu nhận định.",
    );
    expect(
      evidenceSummary("TYPOLOGY_MAPPING", {
        typology_code: "T05",
        name_vi: "Luân chuyển tiền nhanh",
      }),
    ).toBe("T05 — Luân chuyển tiền nhanh.");
  });
});

describe("formatAmountText", () => {
  it("rút gọn đuôi thập phân của NUMERIC và giữ tên loại tiền", () => {
    expect(formatAmountText("1083674.330000000000000000 Ruble")).toBe("1.083.674,33 Ruble");
  });

  it("giữ nguyên khi không đọc được số", () => {
    expect(formatAmountText("không rõ")).toBe("không rõ");
    expect(formatAmountText(null)).toBe("—");
  });
});

describe("formatAmountText — số đã được máy chủ định dạng", () => {
  it("không đọc nhầm dấu tách hàng nghìn thành tên loại tiền", () => {
    expect(formatAmountText("1 083 674.33 Ruble")).toBe("1.083.674,33 Ruble");
  });

  it("vẫn xử lý được số thô của bản ghi cũ", () => {
    expect(formatAmountText("10924.920000000000000000 US Dollar")).toBe("10.924,92 US Dollar");
  });
});

describe("nhãn cho màn hình nghiệp vụ", () => {
  // Danh sách lấy từ ràng buộc CHECK của cột audit_log.event_type (db/init).
  // Thiếu một mã ở đây là màn hình chuyên viên hiện nguyên "investigation_completed".
  const EVENT_TYPES = [
    "agent_query", "alert_raised", "case_state_changed", "case_assigned",
    "submitted_for_approval", "approved", "rejected", "more_info_requested",
    "file_exported", "case_viewed", "user_login", "setting_changed", "user_changed",
    "sar_updated", "validation_run", "investigation_started", "investigation_completed",
    "investigation_failed", "investigation_reviewed",
  ];

  it.each(EVENT_TYPES)("mã sự kiện %s có nhãn tiếng Việt", (eventType) => {
    const label = auditEventLabel(eventType);
    expect(label).not.toBe(eventType);
    expect(label).not.toMatch(/_/);
  });

  it("tác nhân là tiến trình thì hiện tên đọc được, không hiện mã", () => {
    expect(actorLabel("api")).toBe("Hệ thống");
    expect(actorLabel("investigation-worker")).toBe("Trợ lý điều tra");
    // Tên tác vụ nội bộ do người vận hành đặt cũng không được lọt ra màn hình.
    expect(actorLabel("chay-lai-dong-bo")).toBe("Hệ thống");
  });

  it("người dùng thật thì hiện họ tên, không hiện mã", () => {
    expect(actorLabel("U-001", "Nguyễn Quang Hưng")).toBe("Nguyễn Quang Hưng");
    expect(actorLabel("U-001")).toBe("Hệ thống");
  });
});

describe("kênh thanh toán và hồ sơ chủ thể", () => {
  it("hợp nhất hai cách ghi của hai bộ dữ liệu về một nhãn", () => {
    // IBM ghi CREDIT_CARD, SAML-D ghi "Credit card" — cùng một khái niệm.
    expect(paymentChannelLabel("CREDIT_CARD")).toBe("Thẻ tín dụng");
    expect(paymentChannelLabel("Credit card")).toBe("Thẻ tín dụng");
    expect(paymentChannelLabel("Cash Withdrawal")).toBe("Rút tiền mặt");
    expect(paymentChannelLabel("Cross-border")).toBe("Chuyển tiền quốc tế");
    expect(paymentChannelLabel("ACH")).toBe("Chuyển khoản ACH");
  });

  it("mã lạ thì giữ nguyên chứ không đoán bừa", () => {
    expect(paymentChannelLabel("SEPA_INSTANT")).toBe("SEPA_INSTANT");
    expect(paymentChannelLabel(null)).toBe("—");
  });

  it("thiếu KYC thì không lộ tên bộ dữ liệu nội bộ", () => {
    // Giá trị thật trong DB, mỗi bộ một kiểu — khớp chính xác từng chuỗi là thua.
    expect(profileValueLabel("KYC unavailable - IBM AML HI-Medium")).toBe("Chưa có thông tin KYC");
    expect(profileValueLabel("KYC unavailable - SAML-D")).toBe("Chưa có thông tin KYC");
    expect(profileValueLabel("KYC unavailable — Behaviour batch import")).toBe("Chưa có thông tin KYC");
  });

  it("giữ nguyên nghề nghiệp thật", () => {
    expect(profileValueLabel("Kỹ sư phần mềm")).toBe("Kỹ sư phần mềm");
  });

  it("bản giải thích cũ đã ghi bất biến vẫn đọc ra tiếng Việt", () => {
    expect(
      investigationTextVi("Ngày 17/09/2022, tài khoản chuyển 2 361.08 Canadian Dollar tới 27:8000BC940 qua kênh CREDIT_CARD (mã giao dịch 12317813)."),
    ).toContain("qua kênh thẻ tín dụng");
  });

  it("không đụng vào câu có kênh lạ", () => {
    const text = "Tài khoản chuyển tiền qua kênh SEPA_INSTANT (mã giao dịch 1).";
    expect(investigationTextVi(text)).toBe(text);
  });

  it("số tiền không tự dán đơn vị — nơi gọi phải tự in loại tiền", () => {
    expect(formatMoney(1234567.5)).toBe("1.234.567,5");
    expect(formatMoney(0)).toBe("0");
  });
});

describe("nhật ký xử lý của tác tử", () => {
  // Nguồn thật trong investigation_trace trên production, kèm số lần xuất hiện.
  const SOURCES = [
    "feature_service", "transaction_service", "detection_engine", "typology_registry",
    "graph_detector", "geo_rule_engine", "mega_pna_engine", "transaction_graph_service",
    "anomaly_explanation_service",
  ];

  it.each(SOURCES)("nguồn %s không lọt ra màn hình dưới dạng mã", (source) => {
    const label = evidenceSourceLabel(source);
    expect(label).not.toBe(source);
    expect(label).not.toMatch(/_/);
  });

  it("bộ phát hiện mới cũng có tên đọc được mà không phải sửa bảng tra", () => {
    // Nguồn được sinh ra từ tên bộ phát hiện, nên bảng cứng sẽ thủng.
    expect(evidenceSourceLabel("mega_pna_engine")).toBe("Bộ phát hiện mạng lưới");
    expect(evidenceSourceLabel("geo_rule_engine")).toBe("Bộ phát hiện luật địa lý");
  });

  it("dịch câu bổ sung bằng chứng, không để lại tên dịch vụ", () => {
    const vi = investigationTextVi("Added RULE_TRIGGER from allow-listed source mega_pna_engine.");
    expect(vi).toBe("Đã bổ sung bằng chứng Quy tắc cảnh báo đã kích hoạt từ Bộ phát hiện mạng lưới.");
  });

  it("câu thiếu bằng chứng không nhắc mã bộ phát hiện", () => {
    const vi = investigationTextVi(
      "Bằng chứng bắt buộc cho cảnh báo loại 'mega_pna' còn thiếu; quy trình tự gọi để bản diễn giải có nguồn dẫn.",
    );
    expect(vi).not.toMatch(/mega_pna/);
    expect(vi).toContain("cảnh báo nhóm mạng lưới");
  });
});
