import { useEffect, useState } from "react";
import { Input, Typography } from "antd";
import { useTranslation } from "react-i18next";

interface JsonEditorProps {
  value?: string;
  onChange?: (value: string) => void;
  onValidityChange?: (isValid: boolean) => void;
  placeholder?: string;
  height?: number;
  disabled?: boolean;
}

export function JsonEditor({
  value = "",
  onChange,
  onValidityChange,
  placeholder,
  height = 200,
  disabled,
}: JsonEditorProps) {
  const { t } = useTranslation();
  const [text, setText] = useState<string>(value);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText(value ?? "");
  }, [value]);

  useEffect(() => {
    if (!text || !text.trim()) {
      setError(null);
      onValidityChange?.(true);
      return;
    }
    try {
      JSON.parse(text);
      setError(null);
      onValidityChange?.(true);
    } catch (err) {
      setError(t("common.jsonInvalid"));
      onValidityChange?.(false);
    }
  }, [text, onValidityChange, t]);

  const handleChange = (nextValue: string) => {
    setText(nextValue);
    onChange?.(nextValue);
  };

  return (
    <div>
      <Input.TextArea
        value={text}
        onChange={(event) => handleChange(event.target.value)}
        autoSize={{ minRows: Math.ceil(height / 24), maxRows: 20 }}
        placeholder={placeholder}
        disabled={disabled}
        spellCheck={false}
      />
      {error && (
        <Typography.Text type="danger" style={{ marginTop: 8, display: "block" }}>
          {error}
        </Typography.Text>
      )}
    </div>
  );
}

export default JsonEditor;
