import axios from "axios";
import type { AxiosError, AxiosRequestConfig, AxiosResponse } from "axios";
import { message } from "antd";
import { useAuthStore } from "@/stores";
import type { ApiResponse } from "@/types/api";

const baseURL = import.meta.env.VITE_API_BASE ?? "/api/v1";

export interface ApiErrorPayload {
  code?: string;
  message?: string;
  status?: number;
  data?: unknown;
}

export class ApiError extends Error {
  code?: string;
  status?: number;
  data?: unknown;

  constructor(payload: ApiErrorPayload) {
    super(payload.message || "Request failed");
    this.name = "ApiError";
    this.code = payload.code;
    this.status = payload.status;
    this.data = payload.data;
  }
}

const client = axios.create({
  baseURL,
  timeout: 20000,
  withCredentials: true,
});

client.interceptors.request.use((config: AxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token && config.headers) {
    // eslint-disable-next-line no-param-reassign
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response: AxiosResponse<ApiResponse<unknown>>) => {
    const envelope = response.data;
    if (envelope && typeof envelope === "object" && "code" in envelope) {
      if (envelope.code !== "SUCCESS") {
        const err = new ApiError({
          code: envelope.code,
          message: envelope.message,
          status: response.status,
          data: envelope.data,
        });
        if (envelope.message) {
          message.error(envelope.message);
        }
        throw err;
      }
      return envelope.data as unknown;
    }
    return envelope as unknown;
  },
  (error: AxiosError<ApiResponse<unknown>>) => {
    if (error.response) {
      const { status, data } = error.response;
      if (status === 401) {
        const { clearAuth } = useAuthStore.getState();
        clearAuth();
        if (window.location.pathname !== "/login") {
          window.location.href = "/login";
        }
      }
      const messageText = data?.message || error.message || "Request failed";
      if (messageText) {
        message.error(messageText);
      }
      return Promise.reject(
        new ApiError({
          code: data?.code,
          message: messageText,
          status,
          data: data?.data,
        })
      );
    }
    message.error(error.message || "Network error");
    return Promise.reject(new ApiError({ message: error.message }));
  }
);

export default client;
