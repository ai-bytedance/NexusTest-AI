import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Form,
  Input,
  message,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import JsonEditor from "@/components/JsonEditor";
import { EmptyState } from "@/components/states/EmptyState";
import { ErrorState } from "@/components/states/ErrorState";
import { LoadingSkeleton } from "@/components/states/LoadingSkeleton";
import { listApis, createApi, updateApi, deleteApi, type ApiPayload } from "@/api/apis";
import { useProjects } from "@/hooks/useProjects";
import type { ApiDefinition, HttpMethod } from "@/types/api";
import { formatDateTime } from "@/utils/format";
import { useUnsavedChangesPrompt } from "@/hooks/useUnsavedChangesPrompt";

interface ApiFormValues {
  name: string;
  method: HttpMethod;
  path: string;
  version?: string;
  group_name?: string;
  headers?: string;
  params?: string;
  body?: string;
  mock_example?: string;
}

function stringifyValue(value: Record<string, unknown> | null | undefined): string {
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
  try {
    return JSON.parse(content);
  } catch (error) {
    throw new Error("PARSER_ERROR");
  }
}

const METHOD_OPTIONS: HttpMethod[] = ["GET", "POST", "PUT", "PATCH", "DELETE"];

export default function ProjectApisPage() {
  const { t } = useTranslation(["apis", "common", "states", "projects"]);
  const { selectedProjectId } = useProjects();
  const [form] = Form.useForm<ApiFormValues>();
  const [apis, setApis] = useState<ApiDefinition[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editingApi, setEditingApi] = useState<ApiDefinition | null>(null);

  const hasUnsavedChanges = modalOpen && form.isFieldsTouched();
  useUnsavedChangesPrompt(hasUnsavedChanges);

  const loadApis = useCallback(async () => {
    if (!selectedProjectId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listApis(selectedProjectId);
      setApis(data);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    void loadApis();
  }, [loadApis]);

  const handleCreate = () => {
    setEditingApi(null);
    form.setFieldsValue({
      name: "",
      method: "GET",
      path: "/",
      version: "",
      group_name: "",
      headers: "",
      params: "",
      body: "",
      mock_example: "",
    });
    setModalOpen(true);
  };

  const handleEdit = (record: ApiDefinition) => {
    setEditingApi(record);
    form.setFieldsValue({
      name: record.name,
      method: record.method,
      path: record.path,
      version: record.version,
      group_name: record.group_name ?? "",
      headers: stringifyValue(record.headers),
      params: stringifyValue(record.params),
      body: stringifyValue(record.body),
      mock_example: stringifyValue(record.mock_example),
    });
    setModalOpen(true);
  };

  const closeModal = useCallback(() => {
    setModalOpen(false);
    form.resetFields();
    setEditingApi(null);
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
    if (!selectedProjectId) {
      return;
    }
    try {
      const values = await form.validateFields();
      const payload: ApiPayload = {
        name: values.name,
        method: values.method,
        path: values.path,
        version: values.version || undefined,
        group_name: values.group_name || undefined,
        headers: safeParse(values.headers) ?? {},
        params: safeParse(values.params) ?? {},
        body: safeParse(values.body) ?? {},
        mock_example: safeParse(values.mock_example) ?? {},
      };
      setSubmitting(true);
      if (editingApi) {
        await updateApi(selectedProjectId, editingApi.id, payload);
      } else {
        await createApi(selectedProjectId, payload);
      }
      message.success(t("common:success"));
      closeModal();
      await loadApis();
    } catch (err) {
      if (err instanceof Error && err.message === "PARSER_ERROR") {
        message.error(t("editor:validation.invalidJson"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = (record: ApiDefinition) => {
    if (!selectedProjectId) return;
    Modal.confirm({
      title: t("common:confirmDeleteTitle"),
      content: t("apis:deleteConfirm"),
      okText: t("common:delete"),
      okButtonProps: { danger: true },
      cancelText: t("common:cancel"),
      onOk: async () => {
        try {
          await deleteApi(selectedProjectId, record.id);
          message.success(t("common:success"));
          await loadApis();
        } catch (err) {
          /* handled globally */
        }
      },
    });
  };

  const columns = useMemo(() => {
    return [
      {
        title: t("apis:name"),
        dataIndex: "name",
        key: "name",
        render: (value: string, record: ApiDefinition) => (
          <Space direction="vertical" size={0}>
            <Typography.Text strong>{value}</Typography.Text>
            <Typography.Text type="secondary">{record.path}</Typography.Text>
          </Space>
        ),
      },
      {
        title: t("apis:method"),
        dataIndex: "method",
        key: "method",
        render: (method: HttpMethod) => <Tag color="blue">{method}</Tag>,
      },
      {
        title: t("apis:version"),
        dataIndex: "version",
        key: "version",
        render: (value: string | null) => value ?? "-",
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
        render: (_: unknown, record: ApiDefinition) => (
          <Space>
            <Button size="small" onClick={() => handleEdit(record)}>
              {t("common:edit", { defaultValue: t("apis:edit") })}
            </Button>
            <Button size="small" danger onClick={() => handleDelete(record)}>
              {t("common:delete")}
            </Button>
          </Space>
        ),
      },
    ];
  }, [handleEdit, t]);

  if (!selectedProjectId) {
    return (
      <EmptyState description={t("projects:noProjects")} helpUrl="https://docs.example.com/projects" />
    );
  }

  if (loading) {
    return <LoadingSkeleton />;
  }

  if (error) {
    return <ErrorState description={error.message} onRetry={loadApis} />;
  }

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Space style={{ justifyContent: "space-between", width: "100%" }} align="center">
        <Typography.Title level={4} style={{ margin: 0 }}>
          {t("apis:title")}
        </Typography.Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadApis()}>
            {t("apis:refresh", { defaultValue: t("projects:refresh") })}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            {t("apis:create")}
          </Button>
        </Space>
      </Space>
      {apis.length === 0 ? (
        <EmptyState
          description={t("apis:empty")}
          onAction={handleCreate}
          actionLabel={t("apis:create")}
          helpUrl="https://docs.example.com/apis"
        />
      ) : (
        <Table<ApiDefinition>
          rowKey="id"
          dataSource={apis}
          columns={columns}
          pagination={false}
        />
      )}
      <Modal
        open={modalOpen}
        onCancel={requestCloseModal}
        onOk={handleSubmit}
        okText={t("common:save")}
        cancelText={t("common:cancel")}
        confirmLoading={submitting}
        title={editingApi ? t("apis:edit") : t("apis:create")}
        width={920}
        destroyOnClose
      >
        <Form<ApiFormValues> layout="vertical" form={form} autoComplete="off">
          <Space size="large" style={{ width: "100%" }} direction="vertical">
            <Form.Item
              label={t("apis:name")}
              name="name"
              rules={[{ required: true, message: t("common:required", { defaultValue: t("common:save") }) }]}
            >
              <Input autoFocus placeholder={t("apis:name") ?? ""} />
            </Form.Item>
            <Space size="large" style={{ width: "100%" }}>
              <Form.Item
                label={t("apis:method")}
                name="method"
                rules={[{ required: true }]}
                style={{ flex: 1 }}
              >
                <Select options={METHOD_OPTIONS.map((method) => ({ value: method, label: method }))} />
              </Form.Item>
              <Form.Item
                label={t("apis:path")}
                name="path"
                rules={[{ required: true }]} 
                style={{ flex: 2 }}
              >
                <Input placeholder="/v1/example" />
              </Form.Item>
            </Space>
            <Space size="large" style={{ width: "100%" }}>
              <Form.Item label={t("apis:version")} name="version" style={{ flex: 1 }}>
                <Input placeholder="v1" />
              </Form.Item>
              <Form.Item label={t("apis:group")} name="group_name" style={{ flex: 1 }}>
                <Input placeholder={t("apis:group") ?? ""} />
              </Form.Item>
            </Space>
            <Form.Item
              label={t("apis:headers")}
              name="headers"
              tooltip={t("apis:headersHint")}
              rules={[{
                validator: (_, value) => {
                  if (!value) return Promise.resolve();
                  try {
                    JSON.parse(value);
                    return Promise.resolve();
                  } catch (err) {
                    return Promise.reject(new Error(t("editor:validation.invalidJson")));
                  }
                },
              }]}
            >
              <JsonEditor schemaKey="api.headers" templatesKey="api.headers" height={220} />
            </Form.Item>
            <Form.Item
              label={t("apis:params")}
              name="params"
              tooltip={t("apis:paramsHint")}
              rules={[{
                validator: (_, value) => {
                  if (!value) return Promise.resolve();
                  try {
                    JSON.parse(value);
                    return Promise.resolve();
                  } catch (err) {
                    return Promise.reject(new Error(t("editor:validation.invalidJson")));
                  }
                },
              }]}
            >
              <JsonEditor schemaKey="api.params" templatesKey="api.params" height={220} />
            </Form.Item>
            <Form.Item
              label={t("apis:body")}
              name="body"
              tooltip={t("apis:bodyHint")}
              rules={[{
                validator: (_, value) => {
                  if (!value) return Promise.resolve();
                  try {
                    JSON.parse(value);
                    return Promise.resolve();
                  } catch (err) {
                    return Promise.reject(new Error(t("editor:validation.invalidJson")));
                  }
                },
              }]}
            >
              <JsonEditor schemaKey="api.body" templatesKey="api.body" height={260} />
            </Form.Item>
            <Form.Item
              label={t("apis:mock")}
              name="mock_example"
              tooltip={t("apis:mockHint")}
              rules={[{
                validator: (_, value) => {
                  if (!value) return Promise.resolve();
                  try {
                    JSON.parse(value);
                    return Promise.resolve();
                  } catch (err) {
                    return Promise.reject(new Error(t("editor:validation.invalidJson")));
                  }
                },
              }]}
            >
              <JsonEditor schemaKey="api.mock" templatesKey="api.mock" height={220} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </Space>
  );
}
