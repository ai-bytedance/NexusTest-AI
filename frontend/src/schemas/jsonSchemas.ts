import type { JSONSchema7 } from "json-schema";

export type JsonSchemaKey =
  | "api.headers"
  | "api.params"
  | "api.body"
  | "api.mock"
  | "case.inputs"
  | "case.expected"
  | "case.assertions"
  | "suite.variables";

export const JSON_SCHEMA_REGISTRY: Record<JsonSchemaKey, JSONSchema7> = {
  "api.headers": {
    type: "object",
    additionalProperties: {
      type: ["string", "number", "boolean"],
    },
    description: "API request headers",
  },
  "api.params": {
    type: "object",
    properties: {
      page: { type: "integer", minimum: 1, description: "Page index" },
      pageSize: { type: "integer", minimum: 1, maximum: 200, description: "Page size" },
    },
    additionalProperties: {
      type: ["string", "number", "boolean"],
    },
  },
  "api.body": {
    type: "object",
    additionalProperties: true,
  },
  "api.mock": {
    type: "object",
    properties: {
      code: { type: "integer" },
      message: { type: "string" },
      data: { type: ["object", "array", "string", "number", "boolean", "null"] },
    },
    required: ["code"],
  },
  "case.inputs": {
    type: "object",
    additionalProperties: true,
  },
  "case.expected": {
    type: ["object", "array", "string", "number", "boolean", "null"],
  },
  "case.assertions": {
    type: "array",
    items: {
      type: "object",
      properties: {
        type: { type: "string", enum: ["status", "json_path", "equals"] },
        target: { type: "string" },
        expected: {},
        comparator: { type: "string" },
      },
      required: ["type"],
      additionalProperties: true,
    },
  },
  "suite.variables": {
    type: "object",
    additionalProperties: {
      type: ["string", "number", "boolean"],
    },
  },
};

export interface JsonTemplate {
  key: string;
  labelKey: string;
  example: string;
}

export const JSON_TEMPLATES: Record<JsonSchemaKey, JsonTemplate[]> = {
  "api.headers": [
    {
      key: "basic",
      labelKey: "apis:templates.headers.basic",
      example: JSON.stringify(
        {
          Authorization: "Bearer <token>",
          "X-Trace-Id": "{{ trace_id }}",
        },
        null,
        2
      ),
    },
  ],
  "api.params": [
    {
      key: "pagination",
      labelKey: "apis:templates.params.pagination",
      example: JSON.stringify(
        {
          page: 1,
          pageSize: 20,
          search: "",
        },
        null,
        2
      ),
    },
  ],
  "api.body": [
    {
      key: "json",
      labelKey: "apis:templates.body.json",
      example: JSON.stringify(
        {
          name: "",
          email: "",
          active: true,
        },
        null,
        2
      ),
    },
  ],
  "api.mock": [
    {
      key: "success",
      labelKey: "apis:templates.mock.success",
      example: JSON.stringify(
        {
          code: 0,
          message: "success",
          data: {
            id: "123",
            items: [],
          },
        },
        null,
        2
      ),
    },
  ],
  "case.inputs": [
    {
      key: "basic",
      labelKey: "cases:templates.inputs.basic",
      example: JSON.stringify(
        {
          userId: "{{ latest_user.id }}",
          retries: 0,
        },
        null,
        2
      ),
    },
  ],
  "case.expected": [],
  "case.assertions": [
    {
      key: "status",
      labelKey: "cases:templates.assertions.status",
      example: JSON.stringify(
        [
          {
            type: "status",
            expected: 200,
          },
        ],
        null,
        2
      ),
    },
    {
      key: "jsonPath",
      labelKey: "cases:templates.assertions.jsonPath",
      example: JSON.stringify(
        [
          {
            type: "json_path",
            target: "$.data.id",
            comparator: "exists",
          },
        ],
        null,
        2
      ),
    },
  ],
  "suite.variables": [
    {
      key: "basic",
      labelKey: "suites:templates.variables.basic",
      example: JSON.stringify(
        {
          environment: "staging",
          retries: 1,
        },
        null,
        2
      ),
    },
  ],
};
