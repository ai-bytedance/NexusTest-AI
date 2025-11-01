import { useCallback, useEffect } from "react";
import { message } from "antd";
import { getProjects } from "@/api/projects";
import i18n from "@/i18n";
import { selectSelectedProject, useProjectStore } from "@/stores";
import type { Project } from "@/types/api";

interface UseProjectsOptions {
  autoLoad?: boolean;
}

export function useProjects(options: UseProjectsOptions = {}) {
  const { autoLoad = true } = options;
  const {
    projects,
    selectedProjectId,
    loading,
    setProjects,
    setSelectedProject,
    setLoading,
  } = useProjectStore();
  const selectedProject = useProjectStore(selectSelectedProject);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getProjects();
      setProjects(data);
      if (data.length > 0 && !selectedProjectId) {
        setSelectedProject(data[0].id);
      } else if (selectedProjectId) {
        const exists = data.some((item) => item.id === selectedProjectId);
        if (!exists && data.length > 0) {
          setSelectedProject(data[0].id);
        }
      }
    } catch (error) {
      message.error(i18n.t("common.failed"));
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId, setLoading, setProjects, setSelectedProject]);

  useEffect(() => {
    if (autoLoad) {
      void refresh();
    }
  }, [autoLoad, refresh]);

  return {
    projects,
    selectedProjectId,
    selectedProject: (selectedProject as Project | null) ?? null,
    loading,
    setSelectedProject,
    refresh,
  };
}
