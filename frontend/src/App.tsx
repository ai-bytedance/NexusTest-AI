import { Navigate, Route, Routes } from "react-router-dom";
import { lazy } from "react";
import AuthLayout from "@/layouts/AuthLayout";
import AppLayout from "@/layouts/AppLayout";
import RequireAuth from "@/router/RequireAuth";

const LoginPage = lazy(() => import("@/pages/LoginPage"));
const DashboardPage = lazy(() => import("@/pages/DashboardPage"));
const ProjectsPage = lazy(() => import("@/pages/ProjectsPage"));
const ProjectApisPage = lazy(() => import("@/pages/ProjectApisPage"));
const ProjectTestCasesPage = lazy(() => import("@/pages/ProjectTestCasesPage"));
const ProjectTestSuitesPage = lazy(() => import("@/pages/ProjectTestSuitesPage"));
const ReportsPage = lazy(() => import("@/pages/ReportsPage"));
const ReportDetailPage = lazy(() => import("@/pages/ReportDetailPage"));

export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <AuthLayout>
            <LoginPage />
          </AuthLayout>
        }
      />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId/apis" element={<ProjectApisPage />} />
        <Route path="projects/:projectId/test-cases" element={<ProjectTestCasesPage />} />
        <Route path="projects/:projectId/test-suites" element={<ProjectTestSuitesPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="reports/:reportId" element={<ReportDetailPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
