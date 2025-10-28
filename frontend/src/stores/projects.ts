import { create } from "zustand";
import type { Project } from "@/types/api";

interface ProjectState {
  projects: Project[];
  selectedProjectId: string | null;
  loading: boolean;
  setProjects: (projects: Project[]) => void;
  setSelectedProject: (projectId: string | null) => void;
  setLoading: (loading: boolean) => void;
}

export const useProjectStore = create<ProjectState>((set) => ({
  projects: [],
  selectedProjectId: null,
  loading: false,
  setProjects: (projects) => set({ projects }),
  setSelectedProject: (selectedProjectId) => set({ selectedProjectId }),
  setLoading: (loading) => set({ loading }),
}));

export const selectSelectedProject = (state: ProjectState): Project | null => {
  const { selectedProjectId, projects } = state;
  if (!selectedProjectId) {
    return null;
  }
  return projects.find((project) => project.id === selectedProjectId) ?? null;
};
