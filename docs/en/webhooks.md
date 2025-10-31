English | [中文](../zh/webhooks.md)

# Webhooks v2

The API Automation Platform provides robust, secure outbound webhooks for key events with HMAC signatures, retry logic, and a delivery console.

## Overview

Webhooks allow you to receive real-time notifications when important events happen in your projects. The system provides:

- **Secure delivery** with HMAC-SHA256 signatures
- **Reliable delivery** with exponential backoff retries
- **Dead Letter Queue (DLQ)** for failed deliveries
- **Delivery console** for monitoring and troubleshooting
- **Extensible event system** for custom integrations

## Supported Events

| Event | Description | Payload Schema |
|-------|-------------|----------------|
| `run.started` | A test run has started | [Run Payload](#run-payload) |
| `run.finished` | A test run has completed | [Run Payload](#run-payload) |
| `import.diff_ready` | An import diff is ready for review | [Import Payload](#import-payload) |
| `import.applied` | An import has been applied | [Import Payload](#import-payload) |
| `issue.created` | A new issue has been created | [Issue Payload](#issue-payload) |
| `issue.updated` | An issue has been updated | [Issue Payload](#issue-payload) |

## Webhook Delivery

### Security

All webhook deliveries are signed with HMAC-SHA256 using your subscription's secret:

1. **Signature Generation**: The signature is generated using the format `{timestamp}.{payload}`
2. **Headers**: Each delivery includes the following headers:
   - `X-NT-Signature`: `sha256=<signature>`
   - `X-NT-Timestamp`: Unix timestamp of the delivery
   - `X-NT-Event`: The event type (e.g., `run.started`)
   - `X-NT-Delivery-ID`: Unique delivery identifier for idempotency

### Retry Logic

Webhooks use intelligent retry logic:

- **Server errors (5xx)**: Automatically retried with exponential backoff
- **Client errors (4xx)**: Not retried (considered permanent failures)
- **Network errors**: Retried with exponential backoff
- **Max retries**: Configurable per subscription (default: 5)
- **Backoff strategies**: Exponential, linear, or fixed delay

### Dead Letter Queue

When a webhook exceeds the maximum retry attempts, it's moved to the DLQ for manual inspection and redelivery.

## API Reference

### Subscriptions

#### Create Subscription
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

#### List Subscriptions
```http
GET /api/v1/projects/{project_id}/webhooks?enabled_only=true
```

#### Update Subscription
```http
PATCH /api/v1/projects/{project_id}/webhooks/{subscription_id}
Content-Type: application/json

{
  "enabled": false
}
```

#### Delete Subscription
```http
DELETE /api/v1/projects/{project_id}/webhooks/{subscription_id}
```

#### Test Webhook
```http
POST /api/v1/projects/{project_id}/webhooks/test-send
Content-Type: application/json

{
  "url": "https://example.com/webhook",
  "secret": "your-secret-key",
  "event_type": "run.started"
}
```

### Deliveries

#### List Deliveries
```http
GET /api/v1/projects/{project_id}/deliveries?status=failed&limit=50&offset=0
```

#### Get Delivery
```http
GET /api/v1/projects/{project_id}/deliveries/{delivery_id}
```

#### Redeliver Webhook
```http
POST /api/v1/deliveries/{delivery_id}/redeliver
Content-Type: application/json

{}
```

## Payload Schemas

### Run Payload
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

### Import Payload
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

### Issue Payload
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

## Signature Verification

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
    
    // Check timestamp is within 5 minutes
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
    
    // Process webhook...
    w.WriteHeader(http.StatusOK)
    fmt.Fprintf(w, "OK")
}
```

## Best Practices

1. **Always verify signatures** before processing webhooks
2. **Check timestamps** to prevent replay attacks (5-minute window)
3. **Use the delivery ID** for idempotency when processing
4. **Monitor the delivery console** for failed deliveries
5. **Use test endpoints** before configuring production webhooks
6. **Implement proper error handling** and return appropriate HTTP status codes
7. **Keep secrets secure** and rotate them regularly

## Troubleshooting

### Common Issues

1. **Signature verification fails**
   - Check that you're using the correct secret
   - Ensure you're hashing the exact payload string (including whitespace)
   - Verify timestamp handling

2. **Webhooks not being delivered**
   - Check that the subscription is enabled
   - Verify the URL is accessible from our servers
   - Check the delivery console for error messages

3. **High failure rates**
   - Review your endpoint's response times (should be under 30 seconds)
   - Ensure your server returns appropriate HTTP status codes
   - Check rate limiting on your endpoint

4. **Missing events**
   - Verify the subscription includes the desired event types
   - Check that events are actually occurring in your project

### Monitoring

Use the delivery console to:
- View delivery history and status
- Inspect payload content (secrets redacted)
- Retry failed deliveries
- Monitor delivery latency and success rates

## Rate Limits

- **Subscriptions**: 100 per project
- **Deliveries**: 10,000 per project per hour
- **Retry attempts**: Configurable per subscription (max 20)
- **Timeout**: 30 seconds per delivery attempt

For higher limits, contact support.
