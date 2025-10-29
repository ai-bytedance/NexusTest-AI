# Test Execution Report

## Overview
- **Report ID:** <REPORT-ID>
- **Project ID:** <PROJECT-ID>
- **Entity:** case · <ENTITY-ID>
- **Status:** FAILED
- **Started:** 2024-10-25 10:15:00 UTC
- **Finished:** 2024-10-25 10:15:01 UTC
- **Duration:** 1.50 s
- **Assertions:** 1/2 (50.0%)
- **Response Size:** 37.00 B
- **Redacted Fields:** authorization, password, secret, token

## Summary
Automated execution summary.

## Steps

### Step 1 · Execution
- Status: Failed
- Case ID: <ENTITY-ID>
- Assertions: 2
- Duration: 1.50 s
- Response Size: 37.00 B
- Runner Status: failed

## Assertions
- Total: 2
- Passed: 1
- Failed: 1
- Pass Rate: 50.0%

| Name | Operator | Result | Notes |
| ---- | -------- | ------ | ----- |
| status_code | status_code | ✅ Pass | &nbsp; |
| body_equals | equals | ❌ Fail | Body mismatch |

## Failures

### body_equals
- Operator: equals
> Body mismatch

**Expected**
```json
{
  "result": "ok"
}
```

**Actual**
```json
{
  "result": "fail"
}
```

**Diff**
```diff
--- expected
+++ actual
@@ -1 +1 @@
-{"result":"ok"}
+{"result":"fail"}
```

## Requests

### Request 1
```json
{
  "headers": {
    "Authorization": "***"
  },
  "method": "GET",
  "url": "https://api.example.com/data"
}
```

## Responses

### Response 1
```json
{
  "body": {
    "result": "fail"
  },
  "status": 200
}
```

## Metrics
- Execution Duration: 1.50 s
- Response Size: 37.00 B
- Runner Status: failed
- Task ID: task-12345

## Environment
- Name: staging
- Base Url: https://staging.example.com

## Dataset
- Name: sample
- Version: 1.0

## Redaction & Truncation
- Request Truncated: False
- Response Truncated: False
- Redacted Fields: authorization, password, secret, token
