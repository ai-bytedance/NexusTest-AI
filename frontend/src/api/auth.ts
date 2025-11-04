import client from "./client";

export interface LoginPayload {
  email?: string;
  username?: string;
  password: string;
}

export interface LoginResult {
  access_token: string;
  token_type: string;
}

export async function login(payload: LoginPayload): Promise<LoginResult> {
  const response = await client.post<LoginResult>("/auth/login", payload);
  return response;
}
