import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import hmac
import hashlib
import json
from datetime import datetime, timedelta

from app.services.webhooks import WebhookService
from app.models.webhook import (
    WebhookSubscription,
    WebhookDelivery,
    WebhookEventType,
    WebhookDeliveryStatus,
    WebhookBackoffStrategy,
)


class TestWebhookService:
    """Test cases for WebhookService"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return AsyncMock()

    @pytest.fixture
    def webhook_service(self, mock_db):
        """Create webhook service instance"""
        return WebhookService(mock_db)

    @pytest.fixture
    def sample_subscription(self):
        """Sample webhook subscription"""
        return WebhookSubscription(
            id="test-sub-id",
            project_id="test-project-id",
            name="Test Webhook",
            url="https://example.com/webhook",
            secret="test-secret",
            events=["run.started", "run.finished"],
            enabled=True,
            headers={},
            retries_max=5,
            backoff_strategy=WebhookBackoffStrategy.EXPONENTIAL,
            created_by="test-user-id",
        )

    @pytest.fixture
    def sample_delivery(self):
        """Sample webhook delivery"""
        return WebhookDelivery(
            id="test-delivery-id",
            subscription_id="test-sub-id",
            event_type=WebhookEventType.RUN_STARTED,
            payload={"test": "data"},
            status=WebhookDeliveryStatus.PENDING,
            attempts=0,
        )

    @pytest.mark.asyncio
    async def test_create_subscription(self, webhook_service, mock_db):
        """Test creating a webhook subscription"""
        # Arrange
        subscription_data = MagicMock()
        subscription_data.name = "Test Webhook"
        subscription_data.url = "https://example.com/webhook"
        subscription_data.secret = "test-secret"
        subscription_data.events = [WebhookEventType.RUN_STARTED]
        subscription_data.enabled = True
        subscription_data.headers = {}
        subscription_data.retries_max = 5
        subscription_data.backoff_strategy = WebhookBackoffStrategy.EXPONENTIAL

        project_id = "test-project-id"
        created_by = "test-user-id"

        # Act
        with patch('app.services.webhooks.uuid.uuid4', return_value="test-id"):
            result = await webhook_service.create_subscription(
                project_id=project_id,
                subscription_data=subscription_data,
                created_by=created_by,
            )

        # Assert
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_subscription(self, webhook_service, mock_db, sample_subscription):
        """Test getting a webhook subscription"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = sample_subscription
        mock_db.execute.return_value = mock_result

        # Act
        result = await webhook_service.get_subscription(
            subscription_id="test-sub-id",
            project_id="test-project-id",
        )

        # Assert
        assert result == sample_subscription

    @pytest.mark.asyncio
    async def test_list_subscriptions(self, webhook_service, mock_db, sample_subscription):
        """Test listing webhook subscriptions"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = [sample_subscription]
        mock_db.execute.return_value = mock_result

        # Act
        result = await webhook_service.list_subscriptions(
            project_id="test-project-id",
            enabled_only=True,
        )

        # Assert
        assert result == [sample_subscription]

    @pytest.mark.asyncio
    async def test_update_subscription(self, webhook_service, mock_db, sample_subscription):
        """Test updating a webhook subscription"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = sample_subscription
        mock_db.execute.return_value = mock_result

        update_data = MagicMock()
        update_data.model_dump.return_value = {"name": "Updated Webhook"}

        # Act
        result = await webhook_service.update_subscription(
            subscription_id="test-sub-id",
            subscription_data=update_data,
            project_id="test-project-id",
        )

        # Assert
        assert result == sample_subscription
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called()

    @pytest.mark.asyncio
    async def test_delete_subscription(self, webhook_service, mock_db, sample_subscription):
        """Test deleting a webhook subscription"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = sample_subscription
        mock_db.execute.return_value = mock_result

        # Act
        result = await webhook_service.delete_subscription(
            subscription_id="test-sub-id",
            project_id="test-project-id",
        )

        # Assert
        assert result is True
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_create_delivery(self, webhook_service, mock_db):
        """Test creating a webhook delivery"""
        # Arrange
        subscription_id = "test-sub-id"
        event_type = WebhookEventType.RUN_STARTED
        payload = {"test": "data"}

        # Act
        with patch('app.services.webhooks.uuid.uuid4', return_value="test-id"):
            result = await webhook_service.create_delivery(
                subscription_id=subscription_id,
                event_type=event_type,
                payload=payload,
            )

        # Assert
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_event(self, webhook_service, mock_db):
        """Test triggering a webhook event"""
        # Arrange
        subscription1 = MagicMock()
        subscription1.events = ["run.started"]
        subscription1.id = "sub1-id"

        subscription2 = MagicMock()
        subscription2.events = ["run.finished"]
        subscription2.id = "sub2-id"

        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = [subscription1, subscription2]
        mock_db.execute.return_value = mock_result

        # Mock create_delivery and schedule_delivery
        webhook_service.create_delivery = AsyncMock(return_value=MagicMock(id="delivery-id"))
        webhook_service.schedule_delivery = AsyncMock()

        # Act
        await webhook_service.trigger_event(
            event_type=WebhookEventType.RUN_STARTED,
            payload={"test": "data"},
            project_id="test-project-id",
        )

        # Assert
        # Should only create delivery for subscription1 (which has run.started event)
        webhook_service.create_delivery.assert_called_once_with(
            subscription_id="sub1-id",
            event_type=WebhookEventType.RUN_STARTED,
            payload={"test": "data"},
        )
        webhook_service.schedule_delivery.assert_called_once()

    def test_calculate_retry_at_exponential(self, webhook_service):
        """Test exponential backoff calculation"""
        # Act
        result1 = webhook_service._calculate_retry_at("exponential", 1)
        result2 = webhook_service._calculate_retry_at("exponential", 2)
        result3 = webhook_service._calculate_retry_at("exponential", 3)

        # Assert
        # Should be approximately 60s, 120s, 240s with jitter
        assert result1 > datetime.utcnow() + timedelta(seconds=50)
        assert result1 < datetime.utcnow() + timedelta(seconds=70)
        assert result2 > datetime.utcnow() + timedelta(seconds=110)
        assert result2 < datetime.utcnow() + timedelta(seconds=130)
        assert result3 > datetime.utcnow() + timedelta(seconds=230)
        assert result3 < datetime.utcnow() + timedelta(seconds=250)

    def test_calculate_retry_at_linear(self, webhook_service):
        """Test linear backoff calculation"""
        # Act
        result1 = webhook_service._calculate_retry_at("linear", 1)
        result2 = webhook_service._calculate_retry_at("linear", 2)

        # Assert
        # Should be approximately 300s, 600s with jitter
        assert result1 > datetime.utcnow() + timedelta(seconds=250)
        assert result1 < datetime.utcnow() + timedelta(seconds=350)
        assert result2 > datetime.utcnow() + timedelta(seconds=550)
        assert result2 < datetime.utcnow() + timedelta(seconds=650)

    def test_calculate_retry_at_fixed(self, webhook_service):
        """Test fixed backoff calculation"""
        # Act
        result = webhook_service._calculate_retry_at("fixed", 1)

        # Assert
        # Should be approximately 300s with jitter
        assert result > datetime.utcnow() + timedelta(seconds=250)
        assert result < datetime.utcnow() + timedelta(seconds=350)

    @pytest.mark.asyncio
    async def test_deliver_webhook_success(self, webhook_service, mock_db, sample_delivery, sample_subscription):
        """Test successful webhook delivery"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.side_effect = [sample_subscription, sample_delivery]
        mock_db.execute.return_value = mock_result

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch('app.services.webhooks.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            # Act
            result = await webhook_service.deliver_webhook("test-delivery-id")

        # Assert
        assert result is True
        assert sample_delivery.status == WebhookDeliveryStatus.DELIVERED
        assert sample_delivery.delivered_at is not None
        assert sample_delivery.last_error is None
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_deliver_webhook_client_error(self, webhook_service, mock_db, sample_delivery, sample_subscription):
        """Test webhook delivery with client error (4xx)"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.side_effect = [sample_subscription, sample_delivery]
        mock_db.execute.return_value = mock_result

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        with patch('app.services.webhooks.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            # Act
            result = await webhook_service.deliver_webhook("test-delivery-id")

        # Assert
        assert result is False
        assert sample_delivery.status == WebhookDeliveryStatus.FAILED
        assert sample_delivery.attempts == 1
        assert "HTTP 400" in sample_delivery.last_error
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_deliver_webhook_server_error_retry(self, webhook_service, mock_db, sample_delivery, sample_subscription):
        """Test webhook delivery with server error (5xx) - should retry"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.side_effect = [sample_subscription, sample_delivery]
        mock_db.execute.return_value = mock_result

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch('app.services.webhooks.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            # Act
            result = await webhook_service.deliver_webhook("test-delivery-id")

        # Assert
        assert result is False
        assert sample_delivery.status == WebhookDeliveryStatus.FAILED
        assert sample_delivery.attempts == 1
        assert sample_delivery.next_retry_at is not None
        assert "HTTP 500" in sample_delivery.last_error
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_deliver_webhook_max_retries_exceeded(self, webhook_service, mock_db, sample_delivery, sample_subscription):
        """Test webhook delivery when max retries exceeded"""
        # Arrange
        sample_delivery.attempts = 5  # Already at max retries
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.side_effect = [sample_subscription, sample_delivery]
        mock_db.execute.return_value = mock_result

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch('app.services.webhooks.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            # Act
            result = await webhook_service.deliver_webhook("test-delivery-id")

        # Assert
        assert result is False
        assert sample_delivery.status == WebhookDeliveryStatus.DLQ
        assert sample_delivery.attempts == 6
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_deliver_webhook_network_error(self, webhook_service, mock_db, sample_delivery, sample_subscription):
        """Test webhook delivery with network error"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.side_effect = [sample_subscription, sample_delivery]
        mock_db.execute.return_value = mock_result

        with patch('app.services.webhooks.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=Exception("Network error"))

            # Act
            result = await webhook_service.deliver_webhook("test-delivery-id")

        # Assert
        assert result is False
        assert sample_delivery.status == WebhookDeliveryStatus.FAILED
        assert sample_delivery.attempts == 1
        assert "Network error" in sample_delivery.last_error
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_redeliver_webhook(self, webhook_service, mock_db, sample_delivery):
        """Test redelivering a webhook"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = sample_delivery
        mock_db.execute.return_value = mock_result

        webhook_service.schedule_delivery = AsyncMock()

        # Act
        result = await webhook_service.redeliver_webhook("test-delivery-id")

        # Assert
        assert result is True
        assert sample_delivery.status == WebhookDeliveryStatus.PENDING
        assert sample_delivery.attempts == 0
        assert sample_delivery.last_error is None
        assert sample_delivery.next_retry_at is None
        mock_db.commit.assert_called()
        webhook_service.schedule_delivery.assert_called_once_with("test-delivery-id")

    @pytest.mark.asyncio
    async def test_test_webhook_success(self, webhook_service):
        """Test successful webhook test"""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch('app.services.webhooks.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            # Act
            success, message, delivery_id = await webhook_service.test_webhook(
                url="https://example.com/webhook",
                secret="test-secret",
                event_type=WebhookEventType.RUN_STARTED,
            )

        # Assert
        assert success is True
        assert "delivered successfully" in message
        assert delivery_id is not None

    @pytest.mark.asyncio
    async def test_test_webhook_failure(self, webhook_service):
        """Test failed webhook test"""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        with patch('app.services.webhooks.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            # Act
            success, message, delivery_id = await webhook_service.test_webhook(
                url="https://example.com/webhook",
                secret="test-secret",
                event_type=WebhookEventType.RUN_STARTED,
            )

        # Assert
        assert success is False
        assert "HTTP 400" in message
        assert delivery_id is not None

    def test_verify_signature_valid(self, webhook_service):
        """Test signature verification with valid signature"""
        # Arrange
        payload = '{"test": "data"}'
        secret = "test-secret"
        timestamp = int(datetime.utcnow().timestamp())
        
        # Generate valid signature
        signature_payload = f"{timestamp}.{payload}"
        signature = hmac.new(
            secret.encode(),
            signature_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        signature = f"sha256={signature}"

        # Act
        result = WebhookService.verify_signature(
            payload=payload,
            signature=signature,
            secret=secret,
            timestamp=timestamp,
        )

        # Assert
        assert result is True

    def test_verify_signature_invalid(self, webhook_service):
        """Test signature verification with invalid signature"""
        # Arrange
        payload = '{"test": "data"}'
        secret = "test-secret"
        timestamp = int(datetime.utcnow().timestamp())
        signature = "sha256=invalid"

        # Act
        result = WebhookService.verify_signature(
            payload=payload,
            signature=signature,
            secret=secret,
            timestamp=timestamp,
        )

        # Assert
        assert result is False

    def test_verify_signature_old_timestamp(self, webhook_service):
        """Test signature verification with old timestamp"""
        # Arrange
        payload = '{"test": "data"}'
        secret = "test-secret"
        timestamp = int((datetime.utcnow() - timedelta(minutes=10)).timestamp())  # 10 minutes ago
        
        # Generate valid signature but old timestamp
        signature_payload = f"{timestamp}.{payload}"
        signature = hmac.new(
            secret.encode(),
            signature_payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        signature = f"sha256={signature}"

        # Act
        result = WebhookService.verify_signature(
            payload=payload,
            signature=signature,
            secret=secret,
            timestamp=timestamp,
        )

        # Assert
        assert result is False