import { Typography } from "antd";
import { useParams } from "react-router-dom";

export default function ReportDetailPage() {
  const { reportId } = useParams<{ reportId: string }>();

  return (
    <Typography.Title level={4}>
      {reportId ? `Report: ${reportId}` : "Report Detail"}
    </Typography.Title>
  );
}
