import { Skeleton } from "antd";

interface LoadingSkeletonProps {
  rows?: number;
}

export function LoadingSkeleton({ rows = 6 }: LoadingSkeletonProps) {
  return <Skeleton active paragraph={{ rows }} />;
}
