import { Eye, EyeOff, Lock } from "lucide-react";
import { useState } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  onForgot: () => void;
}

export function PasswordField({ value, onChange, disabled, onForgot }: Props) {
  const [visible, setVisible] = useState(false);

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <label htmlFor="password" className="text-xs font-semibold text-ink-mid">
          Mật khẩu
        </label>
        <button
          type="button"
          onClick={onForgot}
          className="rounded text-2xs text-primary transition-colors hover:text-primary-hover"
        >
          Quên mật khẩu?
        </button>
      </div>

      <div className="group relative">
        <Lock
          size={16}
          aria-hidden
          className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-low transition-colors group-focus-within:text-primary"
        />
        <input
          id="password"
          name="password"
          type={visible ? "text" : "password"}
          autoComplete="current-password"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="h-[52px] w-full rounded-[11px] border border-line bg-sunken pl-11 pr-11 text-[13.5px] text-ink-hi outline-none transition-[border-color,box-shadow] placeholder:text-ink-dim focus:border-primary-line focus:shadow-[0_0_0_3px_rgba(18,214,197,0.10)] disabled:opacity-60"
        />
        <button
          type="button"
          // Mật khẩu đang hiện là một trạng thái, không phải một nhãn tĩnh —
          // trình đọc màn hình cần biết bấm vào sẽ ra gì.
          aria-label={visible ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
          aria-pressed={visible}
          onClick={() => setVisible((v) => !v)}
          className="absolute right-3 top-1/2 -translate-y-1/2 rounded p-1 text-ink-low transition-colors hover:text-ink-hi"
        >
          {visible ? <EyeOff size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
        </button>
      </div>
    </div>
  );
}
