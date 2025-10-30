import { Flex, Spin, Typography } from "antd";
import { useTranslation } from "react-i18next";

export function FullscreenLoader() {
  const { t } = useTranslation("states");

  return (
    <Flex
      align="center"
      justify="center"
      style={{ minHeight: "60vh", flexDirection: "column", gap: 16 }}
      role="status"
      aria-live="polite"
    >
      <Spin size="large" />
      <Typography.Text type="secondary">{t("loading")}</Typography.Text>
    </Flex>
  );
}
