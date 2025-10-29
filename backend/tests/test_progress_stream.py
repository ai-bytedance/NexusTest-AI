import asyncio
import json

import pytest

from app.services.reports.progress import close_progress_subscription, publish_progress_event, subscribe_to_progress


@pytest.mark.asyncio
async def test_progress_pubsub_round_trip() -> None:
    report_id = "3f2c8a12-0000-0000-0000-progress"
    pubsub = await subscribe_to_progress(report_id)
    try:
        large_payload = {"text": "x" * 5000, "status": "started"}
        event = publish_progress_event(report_id, "started", payload=large_payload)

        assert event["type"] == "started"
        assert event["report_id"] == report_id
        assert event.get("payload") is not None

        message = None
        for _ in range(10):
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if message is not None:
                break
            await asyncio.sleep(0.05)
        assert message is not None, "Expected a published event"

        data = message.get("data")
        assert isinstance(data, str)
        payload = json.loads(data)
        assert payload["report_id"] == report_id
        assert payload["type"] == "started"
        assert payload.get("payload") is not None
        truncated_text = payload["payload"]["text"]
        assert truncated_text.endswith("… (truncated)")
        assert len(truncated_text) < len(large_payload["text"])
    finally:
        await close_progress_subscription(pubsub, report_id)
