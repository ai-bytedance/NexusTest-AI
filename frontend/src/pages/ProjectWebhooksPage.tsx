import React, { useState, useEffect } from "react";
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Switch,
  Select,
  InputNumber,
  Space,
  Tag,
  message,
  Popconfirm,
  Drawer,
  Typography,
  Tabs,
  Alert,
  Divider,
  Row,
  Col,
  Tooltip,
} from "antd";
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  SendOutlined,
  HistoryOutlined,
  ReloadOutlined,
  EyeOutlined,
} from "@ant-design/icons";
import { webhookApi, type WebhookSubscription, type WebhookDelivery } from "@/api/webhooks";
import { selectSelectedProject, useProjectStore } from "@/stores";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const { TabPane } = Tabs;
const { Option } = Select;

const WebhooksPage: React.FC = () => {
  const currentProject = useProjectStore(selectSelectedProject);
  const [subscriptions, setSubscriptions] = useState<WebhookSubscription[]>([]);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [deliveryDrawerVisible, setDeliveryDrawerVisible] = useState(false);
  const [editingSubscription, setEditingSubscription] = useState<WebhookSubscription | null>(null);
  const [selectedDelivery, setSelectedDelivery] = useState<WebhookDelivery | null>(null);
  const [form] = Form.useForm();
  const [testForm] = Form.useForm();
  const [testModalVisible, setTestModalVisible] = useState(false);
  const [activeTab, setActiveTab] = useState("subscriptions");

  const eventTypes = [
    { label: "Run Started", value: "run.started" },
    { label: "Run Finished", value: "run.finished" },
    { label: "Import Diff Ready", value: "import.diff_ready" },
    { label: "Import Applied", value: "import.applied" },
    { label: "Issue Created", value: "issue.created" },
    { label: "Issue Updated", value: "issue.updated" },
  ];

  const statusColors = {
    pending: "processing",
    delivered: "success",
    failed: "error",
    dlq: "warning",
  };

  useEffect(() => {
    if (currentProject) {
      loadSubscriptions();
      loadDeliveries();
    }
  }, [currentProject]);

  const loadSubscriptions = async () => {
    if (!currentProject) return;
    
    setLoading(true);
    try {
      const data = await webhookApi.listSubscriptions(currentProject.id);
      setSubscriptions(data);
    } catch (error) {
      message.error("Failed to load webhook subscriptions");
    } finally {
      setLoading(false);
    }
  };

  const loadDeliveries = async () => {
    if (!currentProject) return;
    
    try {
      const response = await webhookApi.listDeliveries(currentProject.id);
      setDeliveries(response.items);
    } catch (error) {
      message.error("Failed to load webhook deliveries");
    }
  };

  const handleCreateSubscription = () => {
    setEditingSubscription(null);
    setModalVisible(true);
    form.resetFields();
  };

  const handleEditSubscription = (subscription: WebhookSubscription) => {
    setEditingSubscription(subscription);
    setModalVisible(true);
    form.setFieldsValue({
      ...subscription,
      backoff_strategy: subscription.backoff_strategy,
    });
  };

  const handleDeleteSubscription = async (subscriptionId: string) => {
    if (!currentProject) return;
    
    try {
      await webhookApi.deleteSubscription(currentProject.id, subscriptionId);
      message.success("Webhook subscription deleted successfully");
      loadSubscriptions();
    } catch (error) {
      message.error("Failed to delete webhook subscription");
    }
  };

  const handleSubmitSubscription = async (values: any) => {
    if (!currentProject) return;
    
    try {
      if (editingSubscription) {
        await webhookApi.updateSubscription(currentProject.id, editingSubscription.id, values);
        message.success("Webhook subscription updated successfully");
      } else {
        await webhookApi.createSubscription(currentProject.id, values);
        message.success("Webhook subscription created successfully");
      }
      setModalVisible(false);
      loadSubscriptions();
    } catch (error) {
      message.error("Failed to save webhook subscription");
    }
  };

  const handleTestWebhook = () => {
    testForm.resetFields();
    setTestModalVisible(true);
  };

  const handleTestSubmit = async (values: any) => {
    if (!currentProject) return;
    
    try {
      const response = await webhookApi.testWebhook(currentProject.id, values);
      if (response.success) {
        message.success("Test webhook sent successfully");
      } else {
        message.error(`Test webhook failed: ${response.message}`);
      }
      setTestModalVisible(false);
    } catch (error) {
      message.error("Failed to send test webhook");
    }
  };

  const handleRedeliver = async (deliveryId: string) => {
    try {
      const response = await webhookApi.redeliverWebhook(deliveryId);
      if (response.success) {
        message.success("Webhook redelivery scheduled successfully");
        loadDeliveries();
      } else {
        message.error(`Failed to redeliver webhook: ${response.message}`);
      }
    } catch (error) {
      message.error("Failed to redeliver webhook");
    }
  };

  const subscriptionColumns = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
    },
    {
      title: "URL",
      dataIndex: "url",
      key: "url",
      render: (url: string) => (
        <Tooltip title={url}>
          <Text ellipsis style={{ maxWidth: 200 }}>
            {url}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: "Events",
      dataIndex: "events",
      key: "events",
      render: (events: string[]) => (
        <Space wrap>
          {events.map(event => (
            <Tag key={event} color="blue">
              {event}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: "Status",
      dataIndex: "enabled",
      key: "enabled",
      render: (enabled: boolean) => (
        <Tag color={enabled ? "green" : "red"}>
          {enabled ? "Enabled" : "Disabled"}
        </Tag>
      ),
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (date: string) => new Date(date).toLocaleDateString(),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record: WebhookSubscription) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => handleEditSubscription(record)}
          >
            Edit
          </Button>
          <Popconfirm
            title="Are you sure you want to delete this webhook subscription?"
            onConfirm={() => handleDeleteSubscription(record.id)}
            okText="Yes"
            cancelText="No"
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const deliveryColumns = [
    {
      title: "Event",
      dataIndex: "event_type",
      key: "event_type",
      render: (event: string) => <Tag color="blue">{event}</Tag>,
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      render: (status: string) => (
        <Tag color={statusColors[status as keyof typeof statusColors]}>
          {status.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: "Attempts",
      dataIndex: "attempts",
      key: "attempts",
    },
    {
      title: "Last Error",
      dataIndex: "last_error",
      key: "last_error",
      render: (error: string) => (
        <Tooltip title={error}>
          <Text ellipsis style={{ maxWidth: 200 }}>
            {error}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (date: string) => new Date(date).toLocaleDateString(),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record: WebhookDelivery) => (
        <Space>
          <Button
            type="link"
            icon={<EyeOutlined />}
            onClick={() => {
              setSelectedDelivery(record);
              setDeliveryDrawerVisible(true);
            }}
          >
            View
          </Button>
          {(record.status === "failed" || record.status === "dlq") && (
            <Button
              type="link"
              icon={<ReloadOutlined />}
              onClick={() => handleRedeliver(record.id)}
            >
              Redeliver
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card>
        <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
          <Col>
            <Title level={3}>Webhooks</Title>
            <Paragraph>
              Configure webhook subscriptions to receive real-time notifications about your project events.
            </Paragraph>
          </Col>
          <Col>
            <Space>
              <Button icon={<SendOutlined />} onClick={handleTestWebhook}>
                Test Webhook
              </Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateSubscription}>
                Create Subscription
              </Button>
            </Space>
          </Col>
        </Row>

        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <TabPane tab="Subscriptions" key="subscriptions">
            <Table
              columns={subscriptionColumns}
              dataSource={subscriptions}
              rowKey="id"
              loading={loading}
              pagination={{
                showSizeChanger: true,
                showQuickJumper: true,
                showTotal: (total) => `Total ${total} subscriptions`,
              }}
            />
          </TabPane>
          <TabPane tab="Delivery Console" key="deliveries">
            <Alert
              message="Delivery Console"
              description="Monitor webhook delivery status and retry failed deliveries."
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Table
              columns={deliveryColumns}
              dataSource={deliveries}
              rowKey="id"
              loading={loading}
              pagination={{
                showSizeChanger: true,
                showQuickJumper: true,
                showTotal: (total) => `Total ${total} deliveries`,
              }}
            />
          </TabPane>
        </Tabs>
      </Card>

      {/* Create/Edit Subscription Modal */}
      <Modal
        title={editingSubscription ? "Edit Webhook Subscription" : "Create Webhook Subscription"}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        footer={null}
        width={600}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmitSubscription}
          initialValues={{
            enabled: true,
            retries_max: 5,
            backoff_strategy: "exponential",
            headers: {},
          }}
        >
          <Form.Item
            name="name"
            label="Subscription Name"
            rules={[{ required: true, message: "Please enter a name" }]}
          >
            <Input placeholder="Enter subscription name" />
          </Form.Item>

          <Form.Item
            name="url"
            label="Webhook URL"
            rules={[
              { required: true, message: "Please enter a URL" },
              { type: "url", message: "Please enter a valid URL" },
            ]}
          >
            <Input placeholder="https://example.com/webhook" />
          </Form.Item>

          <Form.Item
            name="secret"
            label="Secret Key"
            rules={[{ required: true, message: "Please enter a secret key" }]}
          >
            <Input.Password placeholder="Enter a secret key for signature verification" />
          </Form.Item>

          <Form.Item
            name="events"
            label="Events"
            rules={[{ required: true, message: "Please select at least one event" }]}
          >
            <Select mode="multiple" placeholder="Select events to subscribe to">
              {eventTypes.map(type => (
                <Option key={type.value} value={type.value}>
                  {type.label}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="headers"
            label="Custom Headers"
          >
            <TextArea
              rows={3}
              placeholder='{"Authorization": "Bearer token"}'
            />
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="retries_max"
                label="Max Retries"
                rules={[{ required: true, message: "Please enter max retries" }]}
              >
                <InputNumber min={0} max={20} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="backoff_strategy"
                label="Backoff Strategy"
                rules={[{ required: true, message: "Please select a backoff strategy" }]}
              >
                <Select>
                  <Option value="exponential">Exponential</Option>
                  <Option value="linear">Linear</Option>
                  <Option value="fixed">Fixed</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="enabled" valuePropName="checked">
            <Switch checkedChildren="Enabled" unCheckedChildren="Disabled" />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                {editingSubscription ? "Update" : "Create"}
              </Button>
              <Button onClick={() => setModalVisible(false)}>
                Cancel
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Test Webhook Modal */}
      <Modal
        title="Test Webhook"
        open={testModalVisible}
        onCancel={() => setTestModalVisible(false)}
        footer={null}
      >
        <Form form={testForm} layout="vertical" onFinish={handleTestSubmit}>
          <Form.Item
            name="url"
            label="Webhook URL"
            rules={[
              { required: true, message: "Please enter a URL" },
              { type: "url", message: "Please enter a valid URL" },
            ]}
          >
            <Input placeholder="https://example.com/webhook" />
          </Form.Item>

          <Form.Item
            name="secret"
            label="Secret Key"
            rules={[{ required: true, message: "Please enter a secret key" }]}
          >
            <Input.Password placeholder="Enter the secret key" />
          </Form.Item>

          <Form.Item
            name="event_type"
            label="Event Type"
            initialValue="run.started"
          >
            <Select>
              {eventTypes.map(type => (
                <Option key={type.value} value={type.value}>
                  {type.label}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                Send Test
              </Button>
              <Button onClick={() => setTestModalVisible(false)}>
                Cancel
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Delivery Details Drawer */}
      <Drawer
        title="Webhook Delivery Details"
        placement="right"
        onClose={() => setDeliveryDrawerVisible(false)}
        open={deliveryDrawerVisible}
        width={600}
      >
        {selectedDelivery && (
          <div>
            <Title level={4}>Delivery Information</Title>
            <Paragraph>
              <Text strong>Delivery ID: </Text>
              <Text code>{selectedDelivery.id}</Text>
            </Paragraph>
            <Paragraph>
              <Text strong>Event Type: </Text>
              <Tag color="blue">{selectedDelivery.event_type}</Tag>
            </Paragraph>
            <Paragraph>
              <Text strong>Status: </Text>
              <Tag color={statusColors[selectedDelivery.status as keyof typeof statusColors]}>
                {selectedDelivery.status.toUpperCase()}
              </Tag>
            </Paragraph>
            <Paragraph>
              <Text strong>Attempts: </Text>
              <Text>{selectedDelivery.attempts}</Text>
            </Paragraph>
            <Paragraph>
              <Text strong>Created: </Text>
              <Text>{new Date(selectedDelivery.created_at).toLocaleString()}</Text>
            </Paragraph>
            {selectedDelivery.delivered_at && (
              <Paragraph>
                <Text strong>Delivered: </Text>
                <Text>{new Date(selectedDelivery.delivered_at).toLocaleString()}</Text>
              </Paragraph>
            )}
            {selectedDelivery.last_error && (
              <Paragraph>
                <Text strong>Last Error: </Text>
                <Text type="danger">{selectedDelivery.last_error}</Text>
              </Paragraph>
            )}

            <Divider />

            <Title level={4}>Payload</Title>
            <pre
              style={{
                background: "#f5f5f5",
                padding: 16,
                borderRadius: 4,
                overflow: "auto",
                maxHeight: 300,
              }}
            >
              {JSON.stringify(selectedDelivery.payload, null, 2)}
            </pre>

            {(selectedDelivery.status === "failed" || selectedDelivery.status === "dlq") && (
              <>
                <Divider />
                <Button
                  type="primary"
                  icon={<ReloadOutlined />}
                  onClick={() => {
                    handleRedeliver(selectedDelivery.id);
                    setDeliveryDrawerVisible(false);
                  }}
                >
                  Redeliver
                </Button>
              </>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default WebhooksPage;