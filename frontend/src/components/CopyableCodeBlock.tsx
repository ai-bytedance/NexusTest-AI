import { useCallback, useMemo } from "react";
import { Button, Space, Typography, message } from "antd";
import { CopyOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { stringifyJson } from "@/utils/json";

interface CopyableCodeBlockProps {
  value: unknown;
  language?: string;
  height?: number;
  copyLabel?: string;
}

export function CopyableCodeBlock({
  value,
  language = "json",
  height = 160,
  copyLabel,
}: CopyableCodeBlockProps) {
  const { t } = useTranslation();
  const text = useMemo(() => {
    if (typeof value === "string") {
      return value;
    }
    return stringifyJson(value, 2);
  }, [value]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      message.success(copyLabel ?? t("common.copied"));
    } catch (error) {
      message.error(t("common.failed"));
    }
  }, [copyLabel, t, text]);

  return (
    <div
      style={{
        border: "1px solid #f0f0f0",
        borderRadius: 8,
        background: "#fafafa",
        padding: 12,
      }}
    >
      <Space style={{ marginBottom: 8, justifyContent: "space-between", width: "100%" }}>
        <Typography.Text type="secondary">{language.toUpperCase()}</Typography.Text>
        <Button type="text" size="small" icon={<CopyOutlined />} onClick={handleCopy}>
          {copyLabel ?? t("common.copy")}
        </Button>
      </Space>
      <pre
        style={{
          height,
          margin: 0,
          overflow: "auto",
          fontSize: 12,
          lineHeight: 1.5,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {text}
      </pre>
    </div>
  );
}

export default CopyableCodeBlock;
