import { Button, Empty, Space, Typography } from "antd";
import { useTranslation } from "react-i18next";

interface EmptyStateProps {
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  helpUrl?: string;
}

export function EmptyState({ description, actionLabel, onAction, helpUrl }: EmptyStateProps) {
  const { t } = useTranslation(["states", "common", "app"]);

  return (
    <Space direction="vertical" align="center" style={{ width: "100%", padding: "48px 0" }}>
      <Empty description={description ?? t("states:empty")} />
      <Space>
        {onAction && (
          <Button type="primary" onClick={onAction}>
            {actionLabel ?? t("common:apply")}
          </Button>
        )}
        {helpUrl && (
          <Button href={helpUrl} target="_blank" rel="noreferrer">
            {t("states:viewDocs")}
          </Button>
        )}
      </Space>
    </Space>
  );
}
