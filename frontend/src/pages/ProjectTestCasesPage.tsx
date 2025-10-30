import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Form, Input, Modal, Select, Space, Table, Typography, message } from "antd";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import JsonEditor from "@/components/JsonEditor";
import { EmptyState } from "@/components/states/EmptyState";
import { ErrorState } from "@/components/states/ErrorState";
import { LoadingSkeleton } from "@/components/states/LoadingSkeleton";
import { useProjects } from "@/hooks/useProjects";
import { useUnsavedChangesPrompt } from "@/hooks/useUnsavedChangesPrompt";
import { listApis } from "@/api/apis";
import {
  createTestCase,
  deleteTestCase,
  listTestCases,
  updateTestCase,
  type CreateCasePayload,
} from "@/api/cases";
import type { ApiDefinition, TestCase } from "@/types/api";
import { formatDateTime } from "@/utils/format";

interface CaseFormValues {
  name: string;
  api_id: string;
  inputs?: string;
  expected?: string;
  assertions?: string;
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

function stringifyAssertions(value: Record<string, unknown>[] | null | undefined): string {
  if (!value || value.length === 0) {
    return "";
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch (error) {
    return "";
  }
}

function safeParse<T>(content?: string): T | undefined {
  if (!content || !content.trim()) {
    return undefined;
  }
  return JSON.parse(content) as T;
}

export default function ProjectTestCasesPage() {
  const { t } = useTranslation(["cases", "common", "states", "apis", "projects"]);
  const { selectedProjectId } = useProjects();
  const [form] = Form.useForm<CaseFormValues>();
  const [cases, setCases] = useState<TestCase[]>([]);
  const [apis, setApis] = useState<ApiDefinition[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editingCase, setEditingCase] = useState<TestCase | null>(null);

  const hasUnsavedChanges = modalOpen && form.isFieldsTouched();
  useUnsavedChangesPrompt(hasUnsavedChanges);

  const loadData = useCallback(async () => {
    if (!selectedProjectId) return;
    setLoading(true);
    setError(null);
    try {
      const [caseList, apiList] = await Promise.all([
        listTestCases(selectedProjectId),
        listApis(selectedProjectId),
      ]);
      setCases(caseList);
      setApis(apiList);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleCreate = () => {
    setEditingCase(null);
    form.setFieldsValue({
      name: "",
      api_id: apis[0]?.id ?? "",
      inputs: "",
      expected: "",
      assertions: "",
    });
    setModalOpen(true);
  };

  const handleEdit = (record: TestCase) => {
    setEditingCase(record);
    form.setFieldsValue({
      name: record.name,
      api_id: record.api_id,
      inputs: stringify(record.inputs),
      expected: stringify(record.expected),
      assertions: stringifyAssertions(record.assertions as Record<string, unknown>[] | undefined),
    });
    setModalOpen(true);
  };

  const closeModal = useCallback(() => {
    setModalOpen(false);
    form.resetFields();
    setEditingCase(null);
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
      const payload: CreateCasePayload = {
        name: values.name,
        api_id: values.api_id,
        inputs: safeParse<Record<string, unknown>>(values.inputs) ?? {},
        expected: safeParse<Record<string, unknown>>(values.expected) ?? {},
        assertions: safeParse<Record<string, unknown>[]>(values.assertions) ?? [],
        enabled: true,
      };
      setSubmitting(true);
      if (editingCase) {
        await updateTestCase(selectedProjectId, editingCase.id, payload);
      } else {
        await createTestCase(selectedProjectId, payload);
      }
      message.success(t("common:success"));
      closeModal();
      await loadData();
    } catch (error) {
      if (error instanceof SyntaxError) {
        message.error(t("editor:validation.invalidJson"));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = (record: TestCase) => {
    if (!selectedProjectId) return;
    Modal.confirm({
      title: t("common:confirmDeleteTitle"),
      content: t("cases:deleteConfirm"),
      okText: t("common:delete"),
      okButtonProps: { danger: true },
      cancelText: t("common:cancel"),
      onOk: async () => {
        try {
          await deleteTestCase(selectedProjectId, record.id);
          message.success(t("common:success"));
          await loadData();
        } catch (err) {
          // handled globally
        }
      },
    });
  };

  const columns = useMemo(() => (
    [
      {
        title: t("cases:name"),
        dataIndex: "name",
        key: "name",
        render: (value: string) => <Typography.Text strong>{value}</Typography.Text>,
      },
      {
        title: t("cases:api"),
        dataIndex: "api_id",
        key: "api_id",
        render: (apiId: string) => {
          const api = apis.find((item) => item.id === apiId);
          return api ? `${api.method} ${api.path}` : apiId;
        },
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
        render: (_: unknown, record: TestCase) => (
          <Space>
            <Button size="small" onClick={() => handleEdit(record)}>
              {t("cases:edit")}
            </Button>
            <Button size="small" danger onClick={() => handleDelete(record)}>
              {t("common:delete")}
            </Button>
          </Space>
        ),
      },
    ]
  ), [apis, handleEdit, t]);

  if (!selectedProjectId) {
    return <EmptyState description={t("projects:noProjects")} helpUrl="https://docs.example.com/projects" />;
  }

  if (loading) {
    return <LoadingSkeleton />;
  }

  if (error) {
    return <ErrorState description={error.message} onRetry={loadData} />;
  }

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <Space style={{ justifyContent: "space-between", width: "100%" }} align="center">
        <Typography.Title level={4} style={{ margin: 0 }}>
          {t("cases:title")}
        </Typography.Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadData()}>
            {t("projects:refresh")}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            {t("cases:create")}
          </Button>
        </Space>
      </Space>
      {cases.length === 0 ? (
        <EmptyState
          description={t("cases:empty")}
          onAction={handleCreate}
          actionLabel={t("cases:create")}
          helpUrl="https://docs.example.com/cases"
        />
      ) : (
        <Table<TestCase>
          rowKey="id"
          dataSource={cases}
          columns={columns}
          pagination={false}
        />
      )}
      <Modal
        open={modalOpen}
        title={editingCase ? t("cases:edit") : t("cases:create")}
        onCancel={requestCloseModal}
        onOk={handleSubmit}
        okText={t("common:save")}
        cancelText={t("common:cancel")}
        confirmLoading={submitting}
        width={920}
      >
        <Form<CaseFormValues> layout="vertical" form={form} autoComplete="off">
          <Form.Item
            label={t("cases:name")}
            name="name"
            rules={[{ required: true, message: t("common:required") }]}
          >
            <Input placeholder={t("cases:name") ?? ""} />
          </Form.Item>
          <Form.Item
            label={t("cases:api")}
            name="api_id"
            rules={[{ required: true, message: t("common:required") }]}
          >
            <Select
              options={apis.map((api) => ({
                label: `${api.method} ${api.path}`,
                value: api.id,
              }))}
              placeholder={t("apis:title")}
            />
          </Form.Item>
          <Form.Item
            label={t("cases:inputs")}
            name="inputs"
            tooltip={t("cases:inputsHint")}
          >
            <JsonEditor schemaKey="case.inputs" templatesKey="case.inputs" height={220} />
          </Form.Item>
          <Form.Item
            label={t("cases:expected")}
            name="expected"
            tooltip={t("cases:expectedHint")}
          >
            <JsonEditor schemaKey="case.expected" templatesKey="case.expected" height={220} />
          </Form.Item>
          <Form.Item
            label={t("cases:assertions")}
            name="assertions"
            tooltip={t("cases:assertionsHint")}
          >
            <JsonEditor schemaKey="case.assertions" templatesKey="case.assertions" height={260} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
