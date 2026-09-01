import { useState } from "react";

import { api } from "../../api/client";
import type { ApiCryptoReview } from "../../api/client";
import { formatDateTime } from "../../api/format";

/**
 * Đưa một giao dịch tiền mã hoá vào rà soát và ghi kết luận.
 *
 * Giao dịch Bitcoin KHÔNG trở thành vụ việc ngân hàng: dữ liệu Elliptic đã ẩn
 * danh nên không có tài khoản chủ thể, và một vụ việc rỗng chủ thể thì không
 * điều tra được cũng không xuất được hồ sơ SAR. Đây là hàng đợi riêng — ngắn,
 * ba bước, và kết luận là của con người chứ không phải của mô hình.
 */

export const REVIEW_STATE_LABEL: Record<string, string> = {
  TiepNhan: "Chờ nhận rà soát",
  DangRaSoat: "Đang rà soát",
  KetLuan: "Đã kết luận",
};

export const CONCLUSION_LABEL: Record<string, string> = {
  dang_ngo: "Đáng ngờ",
  khong_dang_ngo: "Không đáng ngờ",
};

/** Nhãn trạng thái rà soát của một giao dịch; chưa vào hàng đợi thì nói vậy. */
export function ReviewChip({ review }: { review: ApiCryptoReview | undefined }) {
  if (!review) {
    return (
      <span className="rounded-control bg-elev px-1.5 py-0.5 text-3xs font-medium text-ink-dim">
        Chưa đưa vào rà soát
      </span>
    );
  }
  const tone =
    review.state === "KetLuan"
      ? review.conclusion === "dang_ngo"
        ? "bg-risk/15 text-risk"
        : "bg-ok/15 text-ok"
      : review.state === "DangRaSoat"
        ? "bg-info/15 text-info"
        : "bg-warn/15 text-warn";
  const label =
    review.state === "KetLuan"
      ? CONCLUSION_LABEL[review.conclusion ?? ""] ?? "Đã kết luận"
      : REVIEW_STATE_LABEL[review.state];
  return <span className={`rounded-control px-1.5 py-0.5 text-3xs font-medium ${tone}`}>{label}</span>;
}

export function ReviewControls({
  txId,
  review,
  currentUserId,
  onChanged,
}: {
  txId: string;
  review: ApiCryptoReview | undefined;
  currentUserId: string | undefined;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [concluding, setConcluding] = useState(false);
  const [conclusion, setConclusion] = useState("dang_ngo");
  const [note, setNote] = useState("");

  const mine = review?.assignee_id && review.assignee_id === currentUserId;

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không thực hiện được, thử lại sau.");
    } finally {
      setBusy(false);
    }
  }

  if (review?.state === "KetLuan") {
    return (
      <div className="mt-2 rounded-control border border-line bg-elev px-3 py-2">
        <div className="text-2xs font-medium text-ink-hi">
          Kết luận: {CONCLUSION_LABEL[review.conclusion ?? ""] ?? "—"}
        </div>
        {review.conclusion_note && (
          <p className="mt-1 text-2xs leading-relaxed text-ink-mid">{review.conclusion_note}</p>
        )}
        <div className="mt-1 text-3xs text-ink-dim">
          {review.concluded_by_name} · {formatDateTime(review.concluded_at)}
        </div>
      </div>
    );
  }

  return (
    <div className="mt-2 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {!review && (
          <button
            type="button"
            disabled={busy}
            onClick={() => void run(() => api.openCryptoReview(txId))}
            className="rounded-control border border-line px-2.5 py-1 text-2xs font-medium text-ink-hi hover:border-line-emphasis disabled:opacity-50"
          >
            Đưa vào rà soát
          </button>
        )}
        {review && !review.assignee_id && (
          <button
            type="button"
            disabled={busy}
            onClick={() => void run(() => api.assignCryptoReview(review.review_id, currentUserId ?? null))}
            className="rounded-control border border-line px-2.5 py-1 text-2xs font-medium text-ink-hi hover:border-line-emphasis disabled:opacity-50"
          >
            Nhận rà soát
          </button>
        )}
        {review && mine && !concluding && (
          <>
            <button
              type="button"
              onClick={() => setConcluding(true)}
              className="rounded-control bg-primary px-2.5 py-1 text-2xs font-semibold text-app hover:bg-primary-hover"
            >
              Ghi kết luận
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void run(() => api.assignCryptoReview(review.review_id, null))}
              className="rounded-control px-2 py-1 text-2xs text-ink-mid hover:text-ink-hi disabled:opacity-50"
            >
              Trả lại hàng đợi
            </button>
          </>
        )}
        {review?.assignee_name && !mine && (
          <span className="text-2xs text-ink-low">Đang rà soát bởi {review.assignee_name}</span>
        )}
      </div>

      {concluding && review && (
        <div className="rounded-control border border-line bg-elev px-3 py-2.5">
          <div className="flex flex-wrap gap-2">
            {Object.entries(CONCLUSION_LABEL).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setConclusion(key)}
                aria-pressed={conclusion === key}
                className={`rounded-control border px-2.5 py-1 text-2xs transition-colors ${
                  conclusion === key
                    ? "border-accent-line bg-accent-soft text-ink-hi"
                    : "border-line text-ink-mid hover:text-ink-hi"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder="Căn cứ của kết luận — bắt buộc, để về sau dựng lại được vì sao."
            className="mt-2 w-full resize-none rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs text-ink-hi placeholder:text-ink-dim focus:border-line-emphasis focus:outline-none"
          />
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setConcluding(false)}
              className="rounded-control px-2 py-1 text-2xs text-ink-mid hover:text-ink-hi"
            >
              Huỷ
            </button>
            <button
              type="button"
              disabled={busy || note.trim().length < 5}
              onClick={() =>
                void run(() =>
                  api.concludeCryptoReview(review.review_id, conclusion, note.trim()),
                ).then(() => setConcluding(false))
              }
              className="rounded-control bg-primary px-2.5 py-1 text-2xs font-semibold text-app hover:bg-primary-hover disabled:opacity-50"
            >
              Lưu kết luận
            </button>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="text-2xs text-warn">
          {error}
        </p>
      )}
    </div>
  );
}
