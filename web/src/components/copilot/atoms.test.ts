import { describe, expect, it } from "vitest";

/**
 * Rút gọn mã hồ sơ. Cùng luật với `CaseId` — tách ở dấu gạch CUỐI CÙNG.
 *
 * Bản đầu giả định mọi mã đều bắt đầu bằng "CASE-AUTO-", nên với dạng mã còn
 * lại của hệ thống nó cho ra một chuỗi DÀI HƠN cả mã gốc và hiện thẳng lên
 * bảng phân công.
 */
function shorten(id: string): string {
  const cut = id.lastIndexOf("-");
  const head = cut > 0 ? id.slice(0, cut) : id;
  const hash = cut > 0 ? id.slice(cut + 1) : "";
  return hash.length > 8 ? `${head}…${hash.slice(-5).toUpperCase()}` : id;
}

describe("rút gọn mã hồ sơ", () => {
  it("mã sinh tự động rút còn tiền tố và năm ký tự cuối", () => {
    expect(shorten("CASE-AUTO-a8f288850ec77e9b3324430e")).toBe("CASE-AUTO…4430E");
  });

  it("dạng mã một đoạn cũng rút đúng, không dài ra", () => {
    const id = "CASE-544e2a92dcac4a4aa49c";
    const short = shorten(id);

    expect(short).toBe("CASE…AA49C");
    expect(short.length).toBeLessThan(id.length);
  });

  it("mã vốn đã ngắn thì giữ nguyên, không thêm dấu ba chấm", () => {
    expect(shorten("CASE-X1")).toBe("CASE-X1");
    expect(shorten("SAR-2026-0182")).toBe("SAR-2026-0182");
  });

  it("mọi mã rút gọn đều ngắn hơn hoặc bằng mã gốc", () => {
    for (const id of [
      "CASE-AUTO-a8f288850ec77e9b3324430e",
      "CASE-544e2a92dcac4a4aa49c",
      "ALT-GEO-5cced52c7a5e3033",
      "SAR-CASE-AUTO-4bc449f086177ba7268f8742",
    ]) {
      expect(shorten(id).length).toBeLessThanOrEqual(id.length);
    }
  });
});
