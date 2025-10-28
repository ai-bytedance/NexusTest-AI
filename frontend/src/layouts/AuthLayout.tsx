import { Layout, Typography } from "antd";
import { useTranslation } from "react-i18next";
import { ReactNode } from "react";

const { Content } = Layout;

interface AuthLayoutProps {
  children: ReactNode;
}

export function AuthLayout({ children }: AuthLayoutProps) {
  const { t } = useTranslation();
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Content
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "48px 16px",
          background: "#f0f2f5",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: 420,
            background: "#fff",
            borderRadius: 16,
            boxShadow: "0 12px 24px rgba(15, 23, 42, 0.08)",
            padding: 32,
          }}
        >
          <Typography.Title level={2} style={{ textAlign: "center", marginBottom: 24 }}>
            {t("app.title")}
          </Typography.Title>
          {children}
        </div>
      </Content>
    </Layout>
  );
}

export default AuthLayout;
