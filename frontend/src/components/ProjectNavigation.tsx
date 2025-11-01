import { Menu } from "antd";
import {
  ApiOutlined,
  FileSearchOutlined,
  SettingOutlined,
  DeploymentUnitOutlined,
  BranchesOutlined,
  BugOutlined,
} from "@ant-design/icons";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useMemo } from "react";

export function ProjectNavigation() {
  const navigate = useNavigate();
  const location = useLocation();
  const { projectId } = useParams<{ projectId: string }>();

  const selectedKey = useMemo(() => {
    const pathname = location.pathname;
    if (pathname.includes("/apis")) return "apis";
    if (pathname.includes("/test-cases")) return "test-cases";
    if (pathname.includes("/test-suites")) return "test-suites";
    if (pathname.includes("/webhooks")) return "webhooks";
    return "apis";
  }, [location.pathname]);

  const menuItems = useMemo(() => [
    {
      key: "apis",
      icon: <ApiOutlined />,
      label: "APIs",
      onClick: () => navigate(`/projects/${projectId}/apis`),
    },
    {
      key: "test-cases",
      icon: <BugOutlined />,
      label: "Test Cases",
      onClick: () => navigate(`/projects/${projectId}/test-cases`),
    },
    {
      key: "test-suites",
      icon: <BranchesOutlined />,
      label: "Test Suites",
      onClick: () => navigate(`/projects/${projectId}/test-suites`),
    },
    {
      key: "webhooks",
      icon: <DeploymentUnitOutlined />,
      label: "Webhooks",
      onClick: () => navigate(`/projects/${projectId}/webhooks`),
    },
  ], [navigate, projectId]);

  if (!projectId) return null;

  return (
    <Menu
      mode="horizontal"
      selectedKeys={[selectedKey]}
      items={menuItems}
      style={{ marginBottom: 16 }}
    />
  );
}

export default ProjectNavigation;