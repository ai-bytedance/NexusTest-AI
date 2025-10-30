import { Layout, Menu, Space, Typography, Button, theme, Tooltip } from "antd";
import {
  AreaChartOutlined,
  ClusterOutlined,
  FileSearchOutlined,
  LogoutOutlined,
  QuestionCircleOutlined,
} from "@ant-design/icons";
import { Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { Suspense, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/stores/auth";
import { useProjects } from "@/hooks/useProjects";
import ProjectSelector from "@/components/ProjectSelector";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { FullscreenLoader } from "@/components/states/FullscreenLoader";

const { Header, Content, Sider } = Layout;
const HELP_URL = "https://docs.example.com/ui-i18n";

export function AppLayout() {
  const { t } = useTranslation(["app", "navigation", "projects", "common"]);
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams();
  const { token } = theme.useToken();
  const { projects, setSelectedProject, selectedProjectId } = useProjects({ autoLoad: true });
  const { userEmail, clearAuth } = useAuthStore((state) => ({
    userEmail: state.userEmail,
    clearAuth: state.clearAuth,
  }));

  useEffect(() => {
    const projectId = params.projectId || params.id;
    if (projectId) {
      setSelectedProject(projectId);
    }
  }, [params.projectId, params.id, setSelectedProject]);

  const pathKey = useMemo(() => {
    if (location.pathname.startsWith("/projects")) {
      return "/projects";
    }
    if (location.pathname.startsWith("/reports")) {
      return "/reports";
    }
    return "/";
  }, [location.pathname]);

  const handleLogout = () => {
    clearAuth();
    navigate("/login", { replace: true });
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider breakpoint="lg" collapsedWidth="0">
        <div
          style={{
            height: 64,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontSize: 18,
            fontWeight: 600,
          }}
        >
          {t("app:title")}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[pathKey]}
          items={[
            { key: "/", icon: <AreaChartOutlined />, label: t("navigation:dashboard") },
            { key: "/projects", icon: <ClusterOutlined />, label: t("navigation:projects") },
            { key: "/reports", icon: <FileSearchOutlined />, label: t("navigation:reports") },
          ]}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: token.colorBgContainer,
            padding: "0 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 16,
          }}
        >
          <Space size={16} wrap>
            <ProjectSelector value={selectedProjectId} />
            <Typography.Text type="secondary">
              {projects.length > 0
                ? `${projects.length} ${t("navigation:projects")}`
                : t("projects:noProjects")}
            </Typography.Text>
          </Space>
          <Space size={16} align="center">
            <LanguageSwitcher />
            <Tooltip title={t("app:docs")}
              placement="bottom"
            >
              <Button
                type="text"
                icon={<QuestionCircleOutlined />}
                href={HELP_URL}
                target="_blank"
                rel="noreferrer"
              />
            </Tooltip>
            {userEmail && <Typography.Text>{t("app:welcome", { email: userEmail })}</Typography.Text>}
            <Button icon={<LogoutOutlined />} onClick={handleLogout} type="primary" danger>
              {t("app:logout")}
            </Button>
          </Space>
        </Header>
        <Content style={{ margin: 24 }}>
          <div
            style={{
              minHeight: 360,
              background: token.colorBgContainer,
              borderRadius: 16,
              padding: 24,
            }}
          >
            <Suspense fallback={<FullscreenLoader />}>
              <Outlet />
            </Suspense>
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}

export default AppLayout;
