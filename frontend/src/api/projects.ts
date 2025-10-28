import client from "./client";
import type {
  Project,
  ProjectMember,
  ProjectRole,
  ProjectWithMembers,
} from "@/types/api";

export interface CreateProjectPayload {
  name: string;
  key: string;
  description?: string | null;
}

export interface UpdateProjectPayload {
  name?: string;
  key?: string;
  description?: string | null;
}

export interface AddMemberPayload {
  email: string;
  role: ProjectRole;
}

export async function getProjects(): Promise<Project[]> {
  return client.get<Project[]>("/v1/projects");
}

export async function getProject(projectId: string): Promise<ProjectWithMembers> {
  return client.get<ProjectWithMembers>(`/v1/projects/${projectId}`);
}

export async function createProject(payload: CreateProjectPayload): Promise<ProjectWithMembers> {
  return client.post<ProjectWithMembers>("/v1/projects", payload);
}

export async function updateProject(
  projectId: string,
  payload: UpdateProjectPayload
): Promise<Project> {
  return client.patch<Project>(`/v1/projects/${projectId}`, payload);
}

export async function deleteProject(
  projectId: string
): Promise<{ id: string; deleted: boolean }> {
  return client.delete<{ id: string; deleted: boolean }>(`/v1/projects/${projectId}`);
}

export async function addProjectMember(
  projectId: string,
  payload: AddMemberPayload
): Promise<ProjectMember> {
  return client.post<ProjectMember>(`/v1/projects/${projectId}/members`, payload);
}

export async function removeProjectMember(
  projectId: string,
  userId: string
): Promise<{ removed_user_id: string }> {
  return client.delete<{ removed_user_id: string }>(
    `/v1/projects/${projectId}/members/${userId}`
  );
}
