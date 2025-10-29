import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  Divider,
  Empty,
  Flex,
  Input,
  List,
  message,
  Row,
  Select,
  Space,
  Spin,
  Tabs,
  Typography,
} from "antd";
import {
  chatWithAssistant,
  getChat,
  listChats,
  saveGeneratedCases,
  type ChatMessageInput,
  type ChatRequestPayload,
} from "@/api/ai";
import { exportPytestSuite } from "@/api/exports";
import { listApis } from "@/api/apis";
import type {
  AIChatMessage,
  AIChatMessageContent,
  AIChatSummary,
  ApiDefinition,
  ChatTool,
  GeneratedCaseOutput,
} from "@/types/api";

const { Title, Paragraph, Text } = Typography;

const TOOL_OPTIONS: { label: string; value: ChatTool }[] = [
  { label: "生成用例", value: "generate_cases" },
  { label: "生成断言", value: "generate_assertions" },
  { label: "生成Mock数据", value: "generate_mock" },
  { label: "总结报告", value: "summarize" },
];

const QUICK_ACTIONS: Array<{ label: string; message: string; tool: ChatTool }> = [
  { label: "插入接口定义", message: "这是接口定义，请分析。", tool: "generate_cases" },
  { label: "为该接口生成5个边界用例", message: "请为该接口生成5个覆盖边界条件的测试用例。", tool: "generate_cases" },
  { label: "为响应示例生成断言", message: "请根据响应示例生成断言。", tool: "generate_assertions" },
  { label: "生成Mock数据", message: "请基于接口模式生成一份mock数据。", tool: "generate_mock" },
];

function requiresApi(tool: ChatTool): boolean {
  return tool === "generate_cases" || tool === "generate_assertions" || tool === "generate_mock";
}

export default function AiAssistantPage() {
  const params = useParams();
  const projectId = params.projectId ?? "";

  const [apis, setApis] = useState<ApiDefinition[]>([]);
  const [sessions, setSessions] = useState<AIChatSummary[]>([]);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<AIChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [selectedTool, setSelectedTool] = useState<ChatTool>("generate_cases");
  const [selectedApi, setSelectedApi] = useState<string | undefined>();
  const [isLoadingChats, setIsLoadingChats] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [lastSavedCaseIds, setLastSavedCaseIds] = useState<string[]>([]);

  useEffect(() => {
    if (!projectId) {
      return;
    }
    let isMounted = true;
    (async () => {
      try {
        const [apiList, chatList] = await Promise.all([listApis(projectId), listChats(projectId)]);
        if (!isMounted) return;
        setApis(apiList);
        setSessions(chatList);
      } catch (error) {
        message.error("加载助手数据失败");
      }
    })();
    return () => {
      isMounted = false;
    };
  }, [projectId]);

  useEffect(() => {
    if (!projectId || !selectedSession) {
      setChatMessages([]);
      return;
    }
    let isMounted = true;
    setIsLoadingChats(true);
    getChat(projectId, selectedSession)
      .then((detail) => {
        if (!isMounted) return;
        setChatMessages(detail.messages);
      })
      .catch(() => message.error("加载会话失败"))
      .finally(() => {
        if (isMounted) setIsLoadingChats(false);
      });
    return () => {
      isMounted = false;
    };
  }, [projectId, selectedSession]);

  const latestAssistantMessage = useMemo(() => {
    return [...chatMessages].reverse().find((msg) => msg.role === "assistant");
  }, [chatMessages]);

  const latestContent: AIChatMessageContent | undefined = latestAssistantMessage?.content;

  const handleRefreshSessions = async () => {
    if (!projectId) return;
    try {
      const data = await listChats(projectId);
      setSessions(data);
    } catch (error) {
      message.error("刷新会话列表失败");
    }
  };

  const handleSendMessage = async () => {
    if (!projectId || !inputValue.trim()) {
      return;
    }
    if (requiresApi(selectedTool) && !selectedApi) {
      message.warning("请选择接口后再执行该操作");
      return;
    }

    const context: ChatRequestPayload["context"] = {};
    if (selectedApi) {
      context.api_id = selectedApi;
      const api = apis.find((item) => item.id === selectedApi);
      if (api && selectedTool === "generate_assertions" && api.mock_example) {
        context.example_response = api.mock_example as Record<string, unknown>;
      }
      if (selectedTool === "generate_mock") {
        context.json_schema = { type: "object" };
      }
    }
    const payload: ChatRequestPayload = {
      project_id: projectId,
      chat_id: selectedSession ?? undefined,
      messages: [
        {
          role: "user",
          content: inputValue,
        } satisfies ChatMessageInput,
      ],
      tools: [selectedTool],
      context: Object.keys(context ?? {}).length ? context : undefined,
    };

    setIsSending(true);
    try {
      const response = await chatWithAssistant(payload);
      const chatId = response.chat.id;
      setSelectedSession(chatId);
      setLastSavedCaseIds([]);
      setInputValue("");
      await Promise.all([handleRefreshSessions(), getChat(projectId, chatId).then((detail) => setChatMessages(detail.messages))]);
    } catch (error) {
      message.error("发送消息失败");
    } finally {
      setIsSending(false);
    }
  };

  const handleSaveCases = async () => {
    if (!projectId || !selectedSession || !latestAssistantMessage || !latestContent) {
      return;
    }
    if (!latestContent.cases || latestContent.cases.length === 0) {
      message.warning("当前回复中没有可保存的用例");
      return;
    }
    const targetApiId = (latestContent.summary?.api_id as string | undefined) ?? selectedApi;
    if (!targetApiId) {
      message.warning("缺少接口上下文，无法保存用例");
      return;
    }
    setIsSaving(true);
    try {
      const response = await saveGeneratedCases(selectedSession, {
        project_id: projectId,
        message_id: latestAssistantMessage.id,
        api_id: targetApiId,
      });
      const ids = response.cases.map((item) => item.id);
      setLastSavedCaseIds(ids);
      message.success(`成功保存 ${ids.length} 条测试用例`);
      await getChat(projectId, selectedSession).then((detail) => setChatMessages(detail.messages));
      await handleRefreshSessions();
    } catch (error) {
      message.error("保存用例失败");
    } finally {
      setIsSaving(false);
    }
  };

  const handleExportPytest = async () => {
    if (!projectId || lastSavedCaseIds.length === 0) {
      message.warning("请先保存需要导出的用例");
      return;
    }
    setIsExporting(true);
    try {
      const blob = await exportPytestSuite({ project_id: projectId, case_ids: lastSavedCaseIds });
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `pytest-export-${Date.now()}.zip`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.URL.revokeObjectURL(url);
      message.success("已导出 Pytest 测试包");
    } catch (error) {
      message.error("导出 Pytest 失败");
    } finally {
      setIsExporting(false);
    }
  };

  const renderStructuredOutput = () => {
    if (!latestContent) {
      return <Empty description="暂无助手回复" />;
    }

    const items = [] as Array<{ key: string; label: string; children: React.ReactNode }>;

    if (latestContent.cases && latestContent.cases.length > 0) {
      items.push({
        key: "cases",
        label: `生成的用例 (${latestContent.cases.length})`,
        children: (
          <List
            dataSource={latestContent.cases}
            bordered
            renderItem={(item: GeneratedCaseOutput, index) => (
              <List.Item key={`${item.name}-${index}`}>
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Text strong>{item.name}</Text>
                  {item.description && <Paragraph>{item.description}</Paragraph>}
                  <Card size="small" title="请求定义">
                    <pre>{JSON.stringify(item.request, null, 2)}</pre>
                  </Card>
                  {item.assertions?.length ? (
                    <Card size="small" title="断言">
                      <pre>{JSON.stringify(item.assertions, null, 2)}</pre>
                    </Card>
                  ) : null}
                  {item.expected && Object.keys(item.expected).length ? (
                    <Card size="small" title="期望结果">
                      <pre>{JSON.stringify(item.expected, null, 2)}</pre>
                    </Card>
                  ) : null}
                </Space>
              </List.Item>
            )}
          />
        ),
      });
    }

    if (latestContent.assertions && latestContent.assertions.length > 0) {
      items.push({
        key: "assertions",
        label: `生成的断言 (${latestContent.assertions.length})`,
        children: <pre>{JSON.stringify(latestContent.assertions, null, 2)}</pre>,
      });
    }

    if (latestContent.mock) {
      items.push({
        key: "mock",
        label: "Mock 数据",
        children: <pre>{JSON.stringify(latestContent.mock, null, 2)}</pre>,
      });
    }

    if (latestContent.summary) {
      items.push({
        key: "summary",
        label: "总结",
        children: <pre>{JSON.stringify(latestContent.summary, null, 2)}</pre>,
      });
    }

    if (items.length === 0) {
      return <Empty description="暂无结构化结果" />;
    }

    return <Tabs items={items} />;
  };

  const apiOptions = apis.map((api) => ({ label: `${api.method} ${api.path}`, value: api.id }));

  return (
    <Row gutter={16} style={{ height: "100%" }}>
      <Col span={6} style={{ borderRight: "1px solid #f0f0f0", paddingRight: 16 }}>
        <Flex justify="space-between" align="center" style={{ marginBottom: 16 }}>
          <Title level={4}>会话列表</Title>
          <Button size="small" onClick={() => setSelectedSession(null)}>
            新建会话
          </Button>
        </Flex>
        <List
          dataSource={sessions}
          renderItem={(item) => (
            <List.Item
              key={item.id}
              onClick={() => setSelectedSession(item.id)}
              style={{
                cursor: "pointer",
                background: item.id === selectedSession ? "#f5f5f5" : undefined,
                borderRadius: 4,
                padding: 12,
              }}
            >
              <Space direction="vertical" size={4} style={{ width: "100%" }}>
                <Text strong>{item.title}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {item.message_count} 条消息
                </Text>
              </Space>
            </List.Item>
          )}
        />
      </Col>

      <Col span={18} style={{ paddingLeft: 16, display: "flex", flexDirection: "column" }}>
        <Card
          title={
            <Space>
              <span>AI 助手</span>
              {selectedSession && <Text type="secondary">会话 ID: {selectedSession}</Text>}
            </Space>
          }
          style={{ flex: 1, marginBottom: 16 }}
        >
          <Spin spinning={isLoadingChats}>
            {chatMessages.length === 0 ? (
              <Empty description="还没有消息" />
            ) : (
              <List
                dataSource={chatMessages}
                renderItem={(messageItem) => (
                  <List.Item key={messageItem.id} style={{ alignItems: "flex-start" }}>
                    <Space direction="vertical" style={{ width: "100%" }}>
                      <Text strong>{messageItem.role === "user" ? "用户" : "助手"}</Text>
                      {messageItem.content?.text && <Paragraph>{messageItem.content.text}</Paragraph>}
                      {messageItem.content?.kind !== "text" && messageItem.role === "assistant" ? (
                        <Card size="small" bordered>
                          <pre style={{ marginBottom: 0 }}>
                            {JSON.stringify(messageItem.content, null, 2)}
                          </pre>
                        </Card>
                      ) : null}
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Spin>
        </Card>

        <Card style={{ marginBottom: 16 }}>{renderStructuredOutput()}</Card>

        <Card>
          <Space direction="vertical" style={{ width: "100%" }} size="large">
            <Row gutter={12}>
              <Col span={10}>
                <Select
                  options={TOOL_OPTIONS}
                  value={selectedTool}
                  onChange={(value) => setSelectedTool(value)}
                  style={{ width: "100%" }}
                />
              </Col>
              <Col span={14}>
                <Select
                  allowClear
                  placeholder="选择接口（部分工具必选）"
                  options={apiOptions}
                  value={selectedApi}
                  onChange={(value) => setSelectedApi(value)}
                  style={{ width: "100%" }}
                />
              </Col>
            </Row>

            <Space wrap>
              {QUICK_ACTIONS.map((action) => (
                <Button
                  key={action.label}
                  size="small"
                  onClick={() => {
                    setSelectedTool(action.tool);
                    setInputValue(action.message);
                  }}
                >
                  {action.label}
                </Button>
              ))}
            </Space>

            <Input.TextArea
              rows={4}
              placeholder="请输入要发送的指令或内容"
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
            />

            <Flex justify="space-between" align="center">
              <Space>
                <Button
                  type="primary"
                  onClick={handleSendMessage}
                  loading={isSending}
                  disabled={!inputValue.trim() || (requiresApi(selectedTool) && !selectedApi)}
                >
                  发送
                </Button>
                <Button
                  onClick={handleSaveCases}
                  disabled={!
                    latestContent?.cases ||
                    latestContent.cases.length === 0 ||
                    !!latestContent.saved_case_ids?.length
                  }
                  loading={isSaving}
                >
                  保存为用例
                </Button>
              </Space>
              <Button
                type="default"
                disabled={lastSavedCaseIds.length === 0}
                loading={isExporting}
                onClick={handleExportPytest}
              >
                导出为 Pytest
              </Button>
            </Flex>
          </Space>
        </Card>
      </Col>
    </Row>
  );
}
