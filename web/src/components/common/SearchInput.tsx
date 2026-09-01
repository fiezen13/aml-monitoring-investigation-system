import { SearchInput as UiSearchInput } from "../ui/Field";

/**
 * Lớp tương thích — ô tìm kiếm thật nằm ở `components/ui/Field`.
 *
 * @deprecated Import `SearchInput` từ `components/ui`.
 */
interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  shortcutHint?: string;
}

export function SearchInput({ value, onChange, placeholder, className, shortcutHint }: SearchInputProps) {
  return (
    <UiSearchInput
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      shortcutHint={shortcutHint}
      className={className}
    />
  );
}
