import { Button, Result } from "antd";
import { useTranslation } from "react-i18next";

interface ErrorStateProps {
  title?: string;
  description?: string;
  onRetry?: () => void;
}

export function ErrorState({ title, description, onRetry }: ErrorStateProps) {
  const { t } = useTranslation(["states", "common"]);

  return (
    <Result
      status="error"
      title={title ?? t("states:error")}
      subTitle={description}
      extra={
        onRetry ? (
          <Button type="primary" onClick={onRetry}>
            {t("states:retry")}
          </Button>
        ) : null
      }
    />
  );
}
