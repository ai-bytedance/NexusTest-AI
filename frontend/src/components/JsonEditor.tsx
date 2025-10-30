import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, Dropdown, Flex, Modal, Space, Tooltip, Typography, message } from "antd";
import type { MenuProps } from "antd";
import { CopyOutlined, CompressOutlined, CodeOutlined, ExpandOutlined, FileSearchOutlined } from "@ant-design/icons";
import Editor, { type OnMount } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { useTranslation } from "react-i18next";
import { JSON_SCHEMA_REGISTRY, JSON_TEMPLATES, type JsonSchemaKey } from "@/schemas";

export interface JsonEditorProps {
  value?: string;
  onChange?: (value: string) => void;
  onValidityChange?: (isValid: boolean) => void;
  schemaKey?: JsonSchemaKey;
  height?: number;
  disabled?: boolean;
  readOnly?: boolean;
  onSave?: (value: string) => void;
  templatesKey?: JsonSchemaKey;
}

const DEFAULT_HEIGHT = 280;

export function JsonEditor({
  value = "",
  onChange,
  onValidityChange,
  schemaKey,
  height = DEFAULT_HEIGHT,
  disabled = false,
  readOnly = false,
  onSave,
  templatesKey,
}: JsonEditorProps) {
  const { t } = useTranslation(["editor", "common"]);
  const [code, setCode] = useState<string>(value ?? "");
  const [showSchema, setShowSchema] = useState(false);
  const [editorInstance, setEditorInstance] = useState<editor.IStandaloneCodeEditor | null>(null);

  const effectiveTemplatesKey = templatesKey ?? schemaKey;

  const schema = useMemo(() => {
    if (!schemaKey) return undefined;
    return JSON_SCHEMA_REGISTRY[schemaKey];
  }, [schemaKey]);

  const templates = useMemo(() => {
    if (!effectiveTemplatesKey) return [];
    return JSON_TEMPLATES[effectiveTemplatesKey] ?? [];
  }, [effectiveTemplatesKey]);

  useEffect(() => {
    setCode(value ?? "");
  }, [value]);

  const handleEditorMount: OnMount = useCallback(
    (instance, monaco) => {
      setEditorInstance(instance);
      if (schema) {
        monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
          validate: true,
          allowComments: true,
          enableSchemaRequest: false,
          schemas: [
            {
              uri: `inmemory://schema/${schemaKey ?? "json"}`,
              fileMatch: [instance.getModel()?.uri.toString() ?? "json"],
              schema,
            },
          ],
        });
      }
      instance.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
        const current = instance.getValue();
        onSave?.(current);
      });
      instance.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyF, () => {
        void instance.getAction("editor.action.formatDocument")?.run();
      });
    },
    [onSave, schema, schemaKey]
  );

  const handleChange = useCallback(
    (nextValue: string | undefined) => {
      const text = nextValue ?? "";
      setCode(text);
      onChange?.(text);
    },
    [onChange]
  );

  const handleValidate = useCallback(
    (markers: editor.IMarker[]) => {
      onValidityChange?.(markers.length === 0);
    },
    [onValidityChange]
  );

  const handleFormat = useCallback(async () => {
    if (!editorInstance) return;
    await editorInstance.getAction("editor.action.formatDocument")?.run();
  }, [editorInstance]);

  const handleMinify = useCallback(() => {
    try {
      if (!code.trim()) {
        setCode("{}");
        onChange?.("{}");
        onValidityChange?.(true);
        return;
      }
      const json = JSON.parse(code);
      const compact = JSON.stringify(json);
      setCode(compact);
      onChange?.(compact);
      onValidityChange?.(true);
      message.success(t("common:success"));
    } catch (err) {
      message.error(t("editor:validation.invalidJson"));
    }
  }, [code, onChange, onValidityChange, t]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
      message.success(t("common:copied"));
    } catch (err) {
      message.error(t("common:error"));
    }
  }, [code, t]);

  const templateMenuItems = useMemo<MenuProps["items"]>(() => {
    if (!templates.length) return [];
    return templates.map((item) => ({
      key: item.key,
      label: t(item.labelKey),
      onClick: () => {
        setCode(item.example);
        onChange?.(item.example);
      },
    }));
  }, [onChange, t, templates]);

  const editorHeight = Math.max(height, 180);

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="small">
      <Flex justify="space-between" align="center">
        <Space>
          <Tooltip title={t("editor:toolbar.format")}>
            <Button icon={<ExpandOutlined />} size="small" onClick={handleFormat} disabled={disabled || readOnly} />
          </Tooltip>
          <Tooltip title={t("editor:toolbar.minify")}>
            <Button icon={<CompressOutlined />} size="small" onClick={handleMinify} disabled={disabled || readOnly} />
          </Tooltip>
          <Tooltip title={t("editor:toolbar.copy")}>
            <Button icon={<CopyOutlined />} size="small" onClick={handleCopy} disabled={disabled} />
          </Tooltip>
          {templateMenuItems.length ? (
            <Dropdown menu={{ items: templateMenuItems }} trigger={["click"]}>
              <Button icon={<CodeOutlined />} size="small" disabled={disabled || readOnly}>
                {t("common:insertTemplate")}
              </Button>
            </Dropdown>
          ) : null}
        </Space>
        {schema ? (
          <Tooltip title={t("editor:toolbar.schema")}>
            <Button icon={<FileSearchOutlined />} size="small" onClick={() => setShowSchema(true)} />
          </Tooltip>
        ) : null}
      </Flex>
      <Editor
        height={editorHeight}
        language="json"
        value={code}
        onMount={handleEditorMount}
        onChange={handleChange}
        onValidate={handleValidate}
        options={{
          readOnly,
          minimap: { enabled: false },
          automaticLayout: true,
          scrollBeyondLastLine: false,
          tabSize: 2,
          formatOnPaste: true,
          formatOnType: true,
        }}
        theme="vs-light"
        path={`${schemaKey ?? "json"}.json`}
      />
      <Modal
        open={showSchema}
        onCancel={() => setShowSchema(false)}
        onOk={() => setShowSchema(false)}
        okText={t("common:close")}
        cancelButtonProps={{ style: { display: "none" } }}
        title={t("common:schema")}
        width={640}
      >
        <Typography.Paragraph>
          <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(schema, null, 2)}</pre>
        </Typography.Paragraph>
      </Modal>
    </Space>
  );
}

export default JsonEditor;
