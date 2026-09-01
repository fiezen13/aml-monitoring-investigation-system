import { useEffect, useState } from "react";

import { api, type GraphNarrative } from "../../../api/client";
import { formatDate } from "../../../api/format";
import { Eyebrow } from "../../../components/fc/primitives";

interface Props {
  accountKey: string | null;
  /** Vụ việc đang mở. Truyền vào để bản kể neo cùng mốc thời gian với bản giải
   *  thích của phiên điều tra; thiếu nó thì hai khối đo trên hai cửa sổ lệch
   *  nhau và cùng một vụ hiện ra hai bộ số. */
  caseId?: string;
  onPickAccount?: (accountKey: string) => void;
}

/**
 * Bản kể của tác tử cho vùng đồ thị đang xem.
 *
 * Vì sao có màn này: đồ thị vẽ đúng nhưng không nói gì. Chuyên viên nhìn vào
 * một mớ đỉnh và mũi tên rồi phải tự trả lời tiền vào từ đâu, đi đâu, ai đứng
 * giữa, vì sao đáng nghi và nên nhìn vào đâu trước. Không ai làm được việc đó
 * trong vài phút, nên cả màn hình trở thành trang trí.
 *
 * Bốn khối dưới đây là bốn câu trả lời ấy, theo đúng thứ tự người ta hỏi.
 */
export function GraphNarrativePanel({ accountKey, caseId, onPickAccount }: Props) {
  const [data, setData] = useState<GraphNarrative | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");

  useEffect(() => {
    if (!accountKey) {
      setData(null);
      setState("idle");
      return;
    }
    let cancelled = false;
    setState("loading");
    api
      .graphNarrative(accountKey, caseId)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setState("idle");
      })
      .catch(() => {
        if (cancelled) return;
        setData(null);
        setState("error");
      });
    // Huỷ theo cờ chứ không theo AbortController: người dùng bấm nhanh qua vài
    // đỉnh thì các lời gọi cũ vẫn về, và chỉ lời gọi cuối được phép ghi kết quả.
    return () => {
      cancelled = true;
    };
  }, [accountKey, caseId]);

  if (!accountKey) return null;

  return (
    <div className="mt-4 animate-up">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <Eyebrow>Tác tử đọc đồ thị</Eyebrow>
        {data && (
          // Nói rõ bản kể do đâu mà có. Người rà soát đang đọc một văn bản sẽ
          // đi vào hồ sơ điều tra; họ có quyền biết nó do mô hình viết hay do
          // phép đo tự dựng.
          <span className="flex-none text-3xs text-ink-dim">
            {data.source === "gemini" ? "mô hình diễn đạt" : "bản đo tự dựng"}
          </span>
        )}
      </div>

      {state === "loading" && <p className="text-3xs text-ink-low">Đang đọc vùng đồ thị quanh tài khoản…</p>}
      {state === "error" && (
        <p className="text-3xs leading-relaxed text-ink-low">
          Chưa đọc được vùng này. Tài khoản có thể không có giao dịch nào trong dữ liệu đang xem.
        </p>
      )}

      {data && (
        <div className="flex flex-col gap-2">
          {/* Nêu rõ CỬA SỔ đã đo. Cùng một tài khoản mở từ trang vụ việc và mở
              từ màn hình đồ thị có thể rơi vào hai khoảng khác nhau; không ghi
              ra thì người đọc thấy hai bộ số mà không hiểu vì sao. */}
          {data.window_start && data.window_end && (
            <p className="text-3xs text-ink-low">
              Số liệu đo trong khoảng {formatDate(data.window_start)} – {formatDate(data.window_end)}.
            </p>
          )}
          <Block title="Tiền vào từ đâu" body={data.flow_in} />
          <Block title="Tiền đi đâu" body={data.flow_out} />

          {data.why_suspicious.length > 0 && (
            <div className="rounded-control border border-warn/30 bg-warn/10 px-2.5 py-2">
              <div className="mb-1 text-3xs font-medium uppercase tracking-wide text-warn-soft">Vì sao đáng nhìn</div>
              <ul className="flex flex-col gap-1">
                {data.why_suspicious.map((line) => (
                  <li key={line} className="text-3xs leading-relaxed text-ink-soft">
                    {line}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data.how_to_read.length > 0 && (
            <div className="rounded-control border border-line bg-sunken px-2.5 py-2">
              <div className="mb-1 text-3xs font-medium uppercase tracking-wide text-ink-dim">Nhìn vào đâu trước</div>
              <ol className="flex flex-col gap-1">
                {data.how_to_read.map((line, index) => (
                  <li key={line} className="flex gap-1.5 text-3xs leading-relaxed text-ink-soft">
                    <span className="flex-none font-mono text-ink-dim">{index + 1}.</span>
                    <span>{line}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {onPickAccount && <Shortcuts data={data} onPickAccount={onPickAccount} />}

          <p className="text-3xs leading-relaxed text-ink-dim">
            Đây là nhận định để hỗ trợ rà soát, không phải kết luận. Mọi con số đều đo trên giao dịch trong khoảng
            đang xét — mở phần bằng chứng để đối chiếu.
          </p>
        </div>
      )}
    </div>
  );
}

function Block({ title, body }: { title: string; body: string }) {
  if (!body) return null;
  return (
    <div className="rounded-control border border-line bg-sunken px-2.5 py-2">
      <div className="mb-1 text-3xs font-medium uppercase tracking-wide text-ink-dim">{title}</div>
      <p className="text-3xs leading-relaxed text-ink-soft">{body}</p>
    </div>
  );
}

/**
 * Lối tắt sang những tài khoản mà bản kể vừa nhắc tên.
 *
 * Bản kể chỉ đường bằng tên tài khoản chứ không bằng vị trí trên màn hình — đồ
 * thị sắp xếp lại mỗi lần vẽ nên "cụm bên trái" là câu vô nghĩa. Nhưng bắt
 * người đọc tự dò một mã như `14821:84C3F0B90` giữa hàng trăm đỉnh thì cũng
 * không hơn gì, nên mỗi tên được nhắc đều thành một nút bấm.
 */
function Shortcuts({ data, onPickAccount }: { data: GraphNarrative; onPickAccount: (key: string) => void }) {
  const reading = data.reading as {
    top_senders?: { account_key: string }[];
    top_receivers?: { account_key: string }[];
  };
  const keys = [
    ...(reading.top_receivers ?? []).map((item) => item.account_key),
    ...(reading.top_senders ?? []).map((item) => item.account_key),
  ].slice(0, 6);
  if (!keys.length) return null;

  return (
    <div>
      <div className="mb-1 text-3xs text-ink-dim">Mở nhanh tài khoản được nhắc tới</div>
      <div className="flex flex-wrap gap-1">
        {keys.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => onPickAccount(key)}
            className="rounded-control border border-line bg-sunken px-1.5 py-0.5 font-mono text-3xs text-ink-soft transition-colors hover:border-line-emphasis hover:text-ink-hi"
          >
            {key}
          </button>
        ))}
      </div>
    </div>
  );
}
