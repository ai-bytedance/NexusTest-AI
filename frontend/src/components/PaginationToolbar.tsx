import { Pagination } from "antd";
import { useTranslation } from "react-i18next";

export interface PaginationState {
  page: number;
  pageSize: number;
  total: number;
}

interface PaginationToolbarProps {
  pagination: PaginationState;
  onChange: (page: number, pageSize: number) => void;
}

export function PaginationToolbar({ pagination, onChange }: PaginationToolbarProps) {
  const { t } = useTranslation();
  return (
    <Pagination
      current={pagination.page}
      pageSize={pagination.pageSize}
      total={pagination.total}
      showQuickJumper
      showSizeChanger
      showTotal={(total) => `${t("common.total", { defaultValue: "Total" })}: ${total}`}
      onChange={onChange}
    />
  );
}

export default PaginationToolbar;
