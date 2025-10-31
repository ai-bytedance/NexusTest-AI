[English](../en/webhooks.md) | 中文

# Webhooks v2

平台提供健壮、安全的 Webhook 出站通知，涵盖 HMAC 签名、指数退避重试与投递控制台。

## 概述

当项目中发生重要事件时，Webhook 允许你实时接收通知。系统具备：

- 基于 HMAC-SHA256 的安全签名
- 指数退避的可靠重试
- 失败投递的死信队列（DLQ）
- 用于监控与排障的投递控制台
- 可扩展的事件系统以便集成

## 支持的事件

| 事件 | 说明 | 负载 Schema |
|------|------|-------------|
| `run.started` | 测试运行开始 | [运行负载](#运行负载) |
| `run.finished` | 测试运行结束 | [运行负载](#运行负载) |
| `import.diff_ready` | 导入差异可供审阅 | [导入负载](#导入负载) |
| `import.applied` | 导入已应用 | [导入负载](#导入负载) |
| `issue.created` | 创建了新问题 | [问题负载](#问题负载) |
| `issue.updated` | 问题已更新 | [问题负载](#问题负载) |

## Webhook 投递

### 安全

所有 Webhook 投递均使用订阅的密钥进行 HMAC-SHA256 签名：

1. 签名生成：格式为 `{timestamp}.{payload}`
2. 请求头包含：
   - `X-NT-Signature`: `sha256=<signature>`
   - `X-NT-Timestamp`: 投递的 Unix 时间戳
   - `X-NT-Event`: 事件类型（如 `run.started`）
   - `X-NT-Delivery-ID`: 唯一投递 ID（幂等）

### 重试策略

- 服务器错误（5xx）：指数退避自动重试
- 客户端错误（4xx）：不重试（视为永久失败）
- 网络错误：指数退避重试
- 最大重试次数：可按订阅配置，默认 5
- 退避策略：指数、线性或固定间隔

### 死信队列

超过最大重试次数后，投递将进入 DLQ 以便人工检查和重新投递。

## API 参考

### 订阅（Subscriptions）

#### 创建订阅
```http
POST /api/v1/projects/{project_id}/webhooks
Content-Type: application/json

{
  "name": "My Webhook",
  "url": "https://example.com/webhook",
  "secret": "your-secret-key",
  "events": ["run.started", "run.finished"],
  "enabled": true,
  "headers": {
    "Authorization": "Bearer token"
  },
  "retries_max": 5,
  "backoff_strategy": "exponential"
}
```

#### 订阅列表
```http
GET /api/v1/projects/{project_id}/webhooks?enabled_only=true
```

#### 更新订阅
```http
PATCH /api/v1/projects/{project_id}/webhooks/{subscription_id}
Content-Type: application/json

{
  "enabled": false
}
```

#### 删除订阅
```http
DELETE /api/v1/projects/{project_id}/webhooks/{subscription_id}
```

#### 测试发送
```http
POST /api/v1/projects/{project_id}/webhooks/test-send
Content-Type: application/json

{
  "url": "https://example.com/webhook",
  "secret": "your-secret-key",
  "event_type": "run.started"
}
```

### 投递（Deliveries）

#### 投递列表
```http
GET /api/v1/projects/{project_id}/deliveries?status=failed&limit=50&offset=0
```

#### 获取投递详情
```http
GET /api/v1/projects/{project_id}/deliveries/{delivery_id}
```

#### 重新投递
```http
POST /api/v1/deliveries/{delivery_id}/redeliver
Content-Type: application/json

{}
```

## 负载结构

### 运行负载
```json
{
  "event_id": "uuid",
  "event_type": "run.started",
  "timestamp": "2024-01-01T00:00:00Z",
  "project": {
    "id": "uuid",
    "name": "My Project",
    "key": "my-project"
  },
  "run": {
    "id": "uuid",
    "status": "running",
    "environment": "production",
    "started_at": "2024-01-01T00:00:00Z",
    "finished_at": null,
    "duration_ms": null,
    "test_count": 42,
    "passed_count": 0,
    "failed_count": 0,
    "skipped_count": 0
  },
  "links": {
    "console": "https://app.example.com/projects/my-project/runs/uuid",
    "api": "https://api.example.com/api/v1/projects/uuid/runs/uuid"
  }
}
```

### 导入负载
```json
{
  "event_id": "uuid",
  "event_type": "import.diff_ready",
  "timestamp": "2024-01-01T00:00:00Z",
  "project": {
    "id": "uuid",
    "name": "My Project",
    "key": "my-project"
  },
  "import": {
    "id": "uuid",
    "status": "diff_ready",
    "source": "github",
    "source_url": "https://github.com/user/repo",
    "branch": "main",
    "commit": "abc123",
    "created_at": "2024-01-01T00:00:00Z",
    "diff_summary": {
      "added": 10,
      "modified": 5,
      "deleted": 2
    }
  },
  "links": {
    "console": "https://app.example.com/projects/my-project/imports/uuid",
    "api": "https://api.example.com/api/v1/projects/uuid/imports/uuid"
  }
}
```

### 问题负载
```json
{
  "event_id": "uuid",
  "event_type": "issue.created",
  "timestamp": "2024-01-01T00:00:00Z",
  "project": {
    "id": "uuid",
    "name": "My Project",
    "key": "my-project"
  },
  "issue": {
    "id": "uuid",
    "title": "Test failure in production",
    "description": "Tests are failing in the production environment",
    "status": "open",
    "severity": "high",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "assignee": null,
    "labels": ["bug", "critical"]
  },
  "links": {
    "console": "https://app.example.com/projects/my-project/issues/uuid",
    "api": "https://api.example.com/api/v1/projects/uuid/issues/uuid"
  }
}
```

## 签名校验

### Node.js
```javascript
const crypto = require('crypto');

function verifySignature(payload, signature, secret, timestamp) {
  const expectedSignature = crypto
    .createHmac('sha256', secret)
    .update(`${timestamp}.${payload}`)
    .digest('hex');
  
  return crypto.timingSafeEqual(
    Buffer.from(signature, 'utf8'),
    Buffer.from(`sha256=${expectedSignature}`, 'utf8')
  );
}

// Express.js middleware example
app.post('/webhook', (req, res) => {
  const signature = req.headers['x-nt-signature'];
  const timestamp = req.headers['x-nt-timestamp'];
  const payload = JSON.stringify(req.body);
  
  if (!verifySignature(payload, signature, process.env.WEBHOOK_SECRET, timestamp)) {
    return res.status(401).send('Invalid signature');
  }
  
  // Process webhook...
  res.status(200).send('OK');
});
```

### Python
```python
import hmac
import hashlib
from flask import Flask, request, abort

def verify_signature(payload, signature, secret, timestamp):
    expected_signature = hmac.new(
        secret.encode(),
        f"{timestamp}.{payload}".encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(
        signature,
        f"sha256={expected_signature}"
    )

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('X-NT-Signature')
    timestamp = request.headers.get('X-NT-Timestamp')
    payload = request.get_data(as_text=True)
    
    if not verify_signature(payload, signature, 'your-secret', timestamp):
        abort(401)
    
    # Process webhook...
    return 'OK'
```

### Go
```go
package main

import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "strconv"
    "time"
)

func verifySignature(payload, signature, secret string, timestamp int64) bool {
    expectedSignature := hmac.New(sha256.New, []byte(secret))
    expectedSignature.Write([]byte(fmt.Sprintf("%d.%s", timestamp, payload)))
    
    return hmac.Equal(
        []byte(signature),
        []byte("sha256="+hex.EncodeToString(expectedSignature.Sum(nil))),
    )
}

func webhookHandler(w http.ResponseWriter, r *http.Request) {
    signature := r.Header.Get("X-NT-Signature")
    timestampStr := r.Header.Get("X-NT-Timestamp")
    
    timestamp, err := strconv.ParseInt(timestampStr, 10, 64)
    if err != nil {
        http.Error(w, "Invalid timestamp", http.StatusBadRequest)
        return
    }
    
    // 检查时间戳是否在 5 分钟窗口内
    if time.Now().Unix()-timestamp > 300 {
        http.Error(w, "Timestamp too old", http.StatusBadRequest)
        return
    }
    
    body, err := io.ReadAll(r.Body)
    if err != nil {
        http.Error(w, "Error reading body", http.StatusInternalServerError)
        return
    }
    
    if !verifySignature(string(body), signature, "your-secret", timestamp) {
        http.Error(w, "Invalid signature", http.StatusUnauthorized)
        return
    }
    
    // 处理 webhook...
    w.WriteHeader(http.StatusOK)
    fmt.Fprintf(w, "OK")
}
```

## 最佳实践

1. 在处理 Webhook 前务必校验签名
2. 检查时间戳以防重放攻击（5 分钟窗口）
3. 使用投递 ID 进行幂等处理
4. 监控投递控制台以排查失败
5. 在生产配置前先使用测试端点
6. 正确处理错误并返回合适的 HTTP 状态码
7. 安全存放密钥并定期轮换

## 故障排查

### 常见问题

1. 签名校验失败
   - 确认使用了正确的密钥
   - 确保对原始负载字符串进行哈希（包括空白）
   - 校验时间戳处理逻辑

2. 未收到 Webhook
   - 检查订阅是否启用
   - 确认 URL 能从我们的服务器访问
   - 查看投递控制台中的错误信息

3. 失败率高
   - 检查端点响应时间（应小于 30 秒）
   - 确保返回合适的 HTTP 状态码
   - 检查端点上的限流

4. 事件缺失
   - 确认订阅包含所需事件类型
   - 确认项目内确实发生了相应事件

### 监控

使用投递控制台可以：
- 查看投递历史与状态
- 检查负载内容（敏感信息已打码）
- 重新投递失败消息
- 监控延迟与成功率

## 速率限制

- 订阅：每个项目 100 个
- 投递：每个项目每小时 10,000 次
- 重试次数：按订阅配置（最多 20）
- 超时：每次投递 30 秒

如需更高配额，请联系支持。
