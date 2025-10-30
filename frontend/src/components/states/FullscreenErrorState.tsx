import { Button, Flex, Typography } from "antd";
import type { FallbackProps } from "react-error-boundary";
import { useTranslation } from "react-i18next";

export function FullscreenErrorState({ error, resetErrorBoundary }: FallbackProps) {
  const { t } = useTranslation("states");

  return (
    <Flex
      align="center"
      justify="center"
      style={{ minHeight: "60vh", flexDirection: "column", gap: 16, padding: 24 }}
      role="alert"
    >
      <Typography.Title level={4} style={{ margin: 0 }}>
        {t("error")}
      </Typography.Title>
      {error?.message ? (
        <Typography.Text type="secondary" style={{ maxWidth: 480, textAlign: "center" }}>
          {error.message}
        </Typography.Text>
      ) : null}
      <Button type="primary" onClick={resetErrorBoundary}>
        {t("retry")}
      </Button>
    </Flex>
  );
}
