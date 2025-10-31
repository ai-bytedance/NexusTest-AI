import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Form, Input, Modal, Space, Table, Typography, message } from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { useProjects } from "@/hooks/useProjects";
import { useUnsavedChangesPrompt } from "@/hooks/useUnsavedChangesPrompt";
import { EmptyState } from "@/components/states/EmptyState";
import { ErrorState } from "@/components/states/ErrorState";
import { LoadingSkeleton } from "@/components/states/LoadingSkeleton";
import JsonEditor from "@/components/JsonEditor";
import {
  createTestSuite,
  deleteTestSuite,
  listTestSuites,
  updateTestSuite,
  type CreateSuitePayload,
} from "@/api/suites";
import type { TestSuite } from "@/types/api";
import { formatDateTime } from "@/utils/format";
import ProjectNavigation from "@/components/ProjectNavigation";

interface SuiteFormValues {
  name: string;
  description?: string;
  variables?: string;
}

function stringify(value: Record<string, unknown> | null | undefined): string {
  if (!value || Object.keys(value).length === 0) {
    return "";
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch (error) {
    return "";
  }
}

function safeParse(content?: string): Record<string, unknown> | undefined {
  if (!content || !content.trim()) {
    return undefined;
  }
  return JSON.parse(content) as Record<string, unknown>;
}

export default function ProjectTestSuitesPage() {
  const { t } = useTranslation(["suites", "common", "states", "projects"]);
  const { selectedProjectId } = useProjects();
  const [form] = Form.useForm<SuiteFormValues>();
  const [suites, setSuites] = useState<TestSuite[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editingSuite, setEditingSuite] = useState<TestSuite | null>(null);

  const hasUnsavedChanges = modalOpen && form.isFieldsTouched();
  useUnsavedChangesPrompt(hasUnsavedChanges);

  const loadSuites = useCallback(async () => {
    if (!selectedProjectId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listTestSuites(selectedProjectId);
      setSuites(data);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    void loadSuites();
  }, [loadSuites]);

  const handleCreate = () => {
    setEditingSuite(null);
    form.setFieldsValue({
      name: "",
      description: "",
      variables: "",
    });
    setModalOpen(true);
  };

  const handleEdit = (record: TestSuite) => {
    setEditingSuite(record);
    form.setFieldsValue({
      name: record.name,
      description: record.description ?? "",
      variables: stringify(record.variables),
    });
    setModalOpen(true);
  };

  const closeModal = useCallback(() => {
    setModalOpen(false);
    form.resetFields();
    setEditingSuite(null);
  }, [form]);

  const requestCloseModal = () => {
    if (form.isFieldsTouched()) {
      Modal.confirm({
        title: t("common:unsavedChangesTitle"),
        content: t("common:unsavedChangesDescription"),
        okText: t("common:leave"),
        cancelText: t("common:stay"),
        onOk: () => closeModal(),
      });
      return;
    }
    closeModal();
  };

  const handleSubmit = async () => {
    if (!selectedProjectId) return;
    try {
      const values = await form.validateFields();
      const payload: CreateSuitePayload = {
        name: values.name,
        description: values.description || undefined,
        variables: safeParse(values.variables) ?? {},
      };
      setSubmitting(true);
      if (editingSuite) {
        await updateTestSuite(selectedProjectId, editingSuite.id, payload);
      } else {
        await createTestSuite(selectedProjectId, payload);
      }
      message.success(t("common:success"));
      closeModal();
      await loadSuites();
    } catch (error) {
      if (error instanceof SyntaxError) {
        message.error(t("editor:validation.invalidJson"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = (record: TestSuite) => {
    if (!selectedProjectId) return;
    Modal.confirm({
      title: t("common:confirmDeleteTitle"),
      content: t("suites:deleteConfirm"),
      okText: t("common:delete"),
      okButtonProps: { danger: true },
      cancelText: t("common:cancel"),
      onOk: async () => {
        try {
          await deleteTestSuite(selectedProjectId, record.id);
          message.success(t("common:success"));
          await loadSuites();
        } catch (err) {
          // handled globally
        }
      },
    });
  };

  const columns = useMemo(() => (
    [
      {
        title: t("suites:name"),
        dataIndex: "name",
        key: "name",
        render: (value: string) => <Typography.Text strong>{value}</Typography.Text>,
      },
      {
        title: t("suites:description"),
        dataIndex: "description",
        key: "description",
        render: (value: string | null) => value || "-",
      },
      {
        title: t("common:updated"),
        dataIndex: "updated_at",
        key: "updated_at",
        render: (value: string) => formatDateTime(value),
      },
      {
        title: t("common:actions"),
        key: "actions",
        render: (_: unknown, record: TestSuite) => (
          <Space>
            <Button size="small" onClick={() => handleEdit(record)}>
              {t("suites:edit")}
            </Button>
            <Button size="small" danger onClick={() => handleDelete(record)}>
              {t("common:delete")}
            </Button>
          </Space>
        ),
      },
    ]
  ), [handleEdit, t]);

  if (!selectedProjectId) {
    return <EmptyState description={t("projects:noProjects")} helpUrl="https://docs.example.com/projects" />;
  }

  if (loading) {
    return <LoadingSkeleton />;
  }

  if (error) {
    return <ErrorState description={error.message} onRetry={loadSuites} />;
  }

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <ProjectNavigation />
      <Space style={{ justifyContent: "space-between", width: "100%" }} align="center">
        <Typography.Title level={4} style={{ margin: 0 }}>
          {t("suites:title")}
        </Typography.Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadSuites()}>
            {t("projects:refresh")}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            {t("suites:create")}
          </Button>
        </Space>
      </Space>
      {suites.length === 0 ? (
        <EmptyState
          description={t("suites:empty")}
          onAction={handleCreate}
          actionLabel={t("suites:create")}
          helpUrl="https://docs.example.com/suites"
        />
      ) : (
        <Table<TestSuite>
          rowKey="id"
          dataSource={suites}
          columns={columns}
          pagination={false}
        />
      )}
      <Modal
        open={modalOpen}
        title={editingSuite ? t("suites:edit") : t("suites:create")}
        onCancel={requestCloseModal}
        onOk={handleSubmit}
        okText={t("common:save")}
        cancelText={t("common:cancel")}
        confirmLoading={submitting}
        width={800}
      >
        <Form<SuiteFormValues> layout="vertical" form={form} autoComplete="off">
          <Form.Item
            label={t("suites:name")}
            name="name"
            rules={[{ required: true, message: t("common:required") }]}
          >
            <Input placeholder={t("suites:name") ?? ""} />
          </Form.Item>
          <Form.Item label={t("suites:description")}
            name="description"
          >
            <Input.TextArea autoSize={{ minRows: 3, maxRows: 6 }} placeholder={t("suites:description") ?? ""} />
          </Form.Item>
          <Form.Item
            label={t("suites:variables")}
            name="variables"
            tooltip={t("suites:variables")}
          >
            <JsonEditor schemaKey="suite.variables" templatesKey="suite.variables" height={240} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
