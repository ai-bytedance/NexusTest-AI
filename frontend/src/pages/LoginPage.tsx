import { useState } from "react";
import { Button, Form, Input, message } from "antd";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { login } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";

interface LoginFormValues {
  email: string;
  password: string;
}

export default function LoginPage() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const setAuth = useAuthStore((state) => state.setAuth);
  const from = (location.state as { from?: Location })?.from?.pathname ?? "/";

  const handleSubmit = async (values: LoginFormValues) => {
    setLoading(true);
    try {
      const result = await login(values);
      setAuth(result.access_token, values.email);
      navigate(from, { replace: true });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Form<LoginFormValues> layout="vertical" autoComplete="off" onFinish={handleSubmit}>
      <Form.Item
        label={t("login.email")}
        name="email"
        rules={[{ required: true, type: "email", message: t("login.email") }]}
      >
        <Input placeholder="user@example.com" size="large" />
      </Form.Item>
      <Form.Item
        label={t("login.password")}
        name="password"
        rules={[{ required: true, message: t("login.password") }]}
      >
        <Input.Password size="large" placeholder="******" />
      </Form.Item>
      <Form.Item>
        <Button type="primary" htmlType="submit" size="large" block loading={loading}>
          {t("login.submit")}
        </Button>
      </Form.Item>
    </Form>
  );
}
