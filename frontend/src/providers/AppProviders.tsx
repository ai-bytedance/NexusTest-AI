import { ReactNode, Suspense } from "react";
import { App as AntApp, ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import enUS from "antd/locale/en_US";
import { useLanguage } from "@/hooks/useLanguage";
import { ErrorBoundary } from "react-error-boundary";
import { FullscreenErrorState } from "@/components/states/FullscreenErrorState";
import { FullscreenLoader } from "@/components/states/FullscreenLoader";

interface AppProvidersProps {
  children: ReactNode;
}

const ANT_LOCALES = {
  zh: zhCN,
  en: enUS,
} as const;

export function AppProviders({ children }: AppProvidersProps) {
  const { language } = useLanguage();

  return (
    <ConfigProvider
      locale={ANT_LOCALES[language]}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: "#1677ff",
        },
      }}
    >
      <AntApp>
        <ErrorBoundary FallbackComponent={FullscreenErrorState}>
          <Suspense fallback={<FullscreenLoader />}>
            {children}
          </Suspense>
        </ErrorBoundary>
      </AntApp>
    </ConfigProvider>
  );
}
