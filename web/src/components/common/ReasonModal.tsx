import { useState } from "react";

import { Modal } from "./Modal";

interface ReasonModalProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: (reason: string) => void;
  onClose: () => void;
  minLength?: number;
}

/**
 * Modal nhập lý do bắt buộc — mọi hành động đổi trạng thái đều đi qua đây (NT3).
 * Lý do được ghi vào audit trail và không sửa lại được.
 */
export function ReasonModal({
  open,
  title,
  description,
  confirmLabel,
  onConfirm,
  onClose,
  minLength = 20,
}: ReasonModalProps) {
  const [reason, setReason] = useState("");
  const valid = reason.trim().length >= minLength;

  const handleConfirm = () => {
    if (!valid) return;
    onConfirm(reason.trim());
    setReason("");
  };

  return (
    <Modal
      open={open}
      title={title}
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="rounded-control border border-line px-3 py-1.5 text-body font-medium text-ink-mid hover:text-ink-hi"
          >
            Hủy
          </button>
          <button
            type="button"
            disabled={!valid}
            onClick={handleConfirm}
            title={
              valid
                ? undefined
                : `Lý do phải có tối thiểu ${minLength} ký tự — ghi vào audit trail, không sửa lại được`
            }
            className="rounded-control bg-primary px-3 py-1.5 text-body font-semibold text-app hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            {confirmLabel}
          </button>
        </>
      }
    >
      <p className="mb-3 text-body text-ink-mid">{description}</p>
      <label className="mb-1 block text-2xs font-semibold uppercase tracking-wide text-ink-mid">
        Lý do (bắt buộc, tối thiểu {minLength} ký tự)
      </label>
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        rows={4}
        className="w-full rounded-control border border-line bg-elev p-2.5 text-body text-ink-hi placeholder:text-ink-low focus:border-primary/50 focus:outline-none"
        placeholder="Căn cứ nghiệp vụ cho quyết định này..."
      />
      <div className="tabular mt-1 text-right text-2xs text-ink-low">
        {reason.trim().length}/{minLength}
      </div>
    </Modal>
  );
}
