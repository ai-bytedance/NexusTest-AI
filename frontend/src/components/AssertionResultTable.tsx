import { Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useTranslation } from "react-i18next";
import type { AssertionItem, AssertionsResult } from "@/types/api";
import StatusTag from "./StatusTag";
import CopyableCodeBlock from "./CopyableCodeBlock";

interface AssertionRow extends AssertionItem {
  key: string;
}

interface AssertionResultTableProps {
  data?: AssertionsResult | null;
  loading?: boolean;
}

export function AssertionResultTable({ data, loading }: AssertionResultTableProps) {
  const { t } = useTranslation();
  const results = Array.isArray(data?.results) ? (data?.results as AssertionItem[]) : [];
  const rows: AssertionRow[] = results.map((item, index) => ({
    key: `${index}`,
    ...item,
  }));

  const columns: ColumnsType<AssertionRow> = [
    {
      title: t("reports.status"),
      dataIndex: "passed",
      key: "passed",
      width: 120,
      render: (passed: boolean | undefined) => (
        <StatusTag status={passed ? "passed" : "failed"} />
      ),
    },
    {
      title: t("reports.assertionName"),
      dataIndex: "name",
      key: "name",
      render: (value: string | undefined) => value || "-",
    },
    {
      title: t("reports.assertionTarget"),
      dataIndex: "target",
      key: "target",
      render: (value: string | undefined) => value || "-",
    },
    {
      title: t("reports.assertionExpected"),
      dataIndex: "expected",
      key: "expected",
      render: (value: unknown) => <CopyableCodeBlock value={value} height={120} />,
    },
    {
      title: t("reports.assertionActual"),
      dataIndex: "actual",
      key: "actual",
      render: (value: unknown) => <CopyableCodeBlock value={value} height={120} />,
    },
    {
      title: t("reports.assertionMessage"),
      dataIndex: "message",
      key: "message",
      render: (value: string | undefined) => value || "-",
    },
  ];

  if (!rows.length) {
    return (
      <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
        {t("reports.noAssertions")}
      </Typography.Paragraph>
    );
  }

  return <Table loading={loading} rowKey="key" columns={columns} dataSource={rows} pagination={false} />;
}

export default AssertionResultTable;
