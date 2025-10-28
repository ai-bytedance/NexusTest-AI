import { ReactNode } from "react";
import { Input, Space } from "antd";
import { useTranslation } from "react-i18next";

interface SearchBarProps {
  value?: string;
  onChange?: (value: string) => void;
  onSearch?: () => void;
  placeholder?: string;
  extra?: ReactNode;
}

export function SearchBar({ value, onChange, onSearch, placeholder, extra }: SearchBarProps) {
  const { t } = useTranslation();
  return (
    <Space style={{ width: "100%", justifyContent: "space-between" }}>
      <Input.Search
        allowClear
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
        onSearch={onSearch}
        placeholder={placeholder ?? t("common.searchPlaceholder")}
        style={{ maxWidth: 360 }}
      />
      {extra}
    </Space>
  );
}

export default SearchBar;
