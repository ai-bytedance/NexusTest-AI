import client from "./client";
import type { ApiResponse } from "@/types/api";

export interface WebhookSubscription {
  id: string;
  project_id: string;
  name: string;
  url: string;
  secret: string;
  events: string[];
  enabled: boolean;
  headers: Record<string, string>;
  retries_max: number;
  backoff_strategy: "exponential" | "linear" | "fixed";
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface WebhookSubscriptionCreate {
  name: string;
  url: string;
  secret: string;
  events: string[];
  enabled?: boolean;
  headers?: Record<string, string>;
  retries_max?: number;
  backoff_strategy?: "exponential" | "linear" | "fixed";
}

export interface WebhookSubscriptionUpdate {
  name?: string;
  url?: string;
  events?: string[];
  enabled?: boolean;
  headers?: Record<string, string>;
  retries_max?: number;
  backoff_strategy?: "exponential" | "linear" | "fixed";
}

export interface WebhookDelivery {
  id: string;
  subscription_id: string;
  event_type: string;
  payload: Record<string, any>;
  status: "pending" | "delivered" | "failed" | "dlq";
  attempts: number;
  last_error?: string;
  next_retry_at?: string;
  delivered_at?: string;
  created_at: string;
  updated_at: string;
}

export interface WebhookDeliveryFilter {
  status?: "pending" | "delivered" | "failed" | "dlq";
  event_type?: string;
  subscription_id?: string;
  created_after?: string;
  created_before?: string;
}

export interface WebhookTestSendRequest {
  url: string;
  secret: string;
  event_type?: string;
}

export interface WebhookTestSendResponse {
  success: boolean;
  message: string;
  delivery_id?: string;
}

export interface WebhookDeliveriesResponse {
  items: WebhookDelivery[];
  total: number;
  limit: number;
  offset: number;
}

export const webhookApi = {
  // Subscriptions
  createSubscription: (
    projectId: string,
    data: WebhookSubscriptionCreate
  ): Promise<WebhookSubscription> =>
    client.post(`/projects/${projectId}/webhooks`, data),

  listSubscriptions: (
    projectId: string,
    enabledOnly?: boolean
  ): Promise<WebhookSubscription[]> =>
    client.get(`/projects/${projectId}/webhooks`, {
      params: { enabled_only: enabledOnly },
    }),

  getSubscription: (
    projectId: string,
    subscriptionId: string
  ): Promise<WebhookSubscription> =>
    client.get(`/projects/${projectId}/webhooks/${subscriptionId}`),

  updateSubscription: (
    projectId: string,
    subscriptionId: string,
    data: WebhookSubscriptionUpdate
  ): Promise<WebhookSubscription> =>
    client.patch(`/projects/${projectId}/webhooks/${subscriptionId}`, data),

  deleteSubscription: (
    projectId: string,
    subscriptionId: string
  ): Promise<void> =>
    client.delete(`/projects/${projectId}/webhooks/${subscriptionId}`),

  testWebhook: (
    projectId: string,
    data: WebhookTestSendRequest
  ): Promise<WebhookTestSendResponse> =>
    client.post(`/projects/${projectId}/webhooks/test-send`, data),

  // Deliveries
  listDeliveries: (
    projectId: string,
    filters: WebhookDeliveryFilter = {},
    limit = 50,
    offset = 0
  ): Promise<WebhookDeliveriesResponse> =>
    client.get(`/projects/${projectId}/deliveries`, {
      params: { ...filters, limit, offset },
    }),

  listSubscriptionDeliveries: (
    projectId: string,
    subscriptionId: string,
    filters: WebhookDeliveryFilter = {},
    limit = 50,
    offset = 0
  ): Promise<WebhookDeliveriesResponse> =>
    client.get(`/projects/${projectId}/webhooks/${subscriptionId}/deliveries`, {
      params: { ...filters, limit, offset },
    }),

  getDelivery: (
    projectId: string,
    deliveryId: string
  ): Promise<WebhookDelivery> =>
    client.get(`/projects/${projectId}/deliveries/${deliveryId}`),

  redeliverWebhook: (deliveryId: string): Promise<{ success: boolean; message: string; delivery_id: string }> =>
    client.post(`/deliveries/${deliveryId}/redeliver`, {}),
};