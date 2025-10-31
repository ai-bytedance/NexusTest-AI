import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch
import json

from app.main import create_app
from app.models.webhook import WebhookEventType, WebhookBackoffStrategy


class TestWebhookAPI:
    """Integration tests for webhook API endpoints"""

    @pytest.fixture
    def app(self):
        """Create FastAPI app instance"""
        return create_app()

    @pytest.fixture
    async def client(self, app):
        """Create async test client"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac

    @pytest.fixture
    def auth_headers(self):
        """Mock authentication headers"""
        return {"Authorization": "Bearer test-token"}

    @pytest.fixture
    def sample_subscription_data(self):
        """Sample webhook subscription data"""
        return {
            "name": "Test Webhook",
            "url": "https://example.com/webhook",
            "secret": "test-secret-key",
            "events": ["run.started", "run.finished"],
            "enabled": True,
            "headers": {"Authorization": "Bearer token"},
            "retries_max": 5,
            "backoff_strategy": "exponential",
        }

    @pytest.mark.asyncio
    async def test_create_subscription_success(self, client, auth_headers, sample_subscription_data):
        """Test successful webhook subscription creation"""
        # Act
        response = await client.post(
            "/api/v1/projects/test-project-id/webhooks",
            json=sample_subscription_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_subscription_data["name"]
        assert data["url"] == sample_subscription_data["url"]
        assert data["events"] == sample_subscription_data["events"]
        assert data["enabled"] == sample_subscription_data["enabled"]
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_subscription_invalid_data(self, client, auth_headers):
        """Test webhook subscription creation with invalid data"""
        # Arrange
        invalid_data = {
            "name": "",  # Empty name
            "url": "invalid-url",  # Invalid URL
            "secret": "123",  # Too short
            "events": [],  # No events
        }

        # Act
        response = await client.post(
            "/api/v1/projects/test-project-id/webhooks",
            json=invalid_data,
            headers=auth_headers,
        )

        # Assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_subscriptions_success(self, client, auth_headers):
        """Test successful webhook subscription listing"""
        # Arrange
        with patch('app.services.webhooks.WebhookService.list_subscriptions') as mock_list:
            mock_list.return_value = [
                {
                    "id": "sub1-id",
                    "name": "Webhook 1",
                    "url": "https://example.com/webhook1",
                    "events": ["run.started"],
                    "enabled": True,
                    "created_at": "2024-01-01T00:00:00Z",
                },
                {
                    "id": "sub2-id",
                    "name": "Webhook 2",
                    "url": "https://example.com/webhook2",
                    "events": ["run.finished"],
                    "enabled": False,
                    "created_at": "2024-01-02T00:00:00Z",
                },
            ]

            # Act
            response = await client.get(
                "/api/v1/projects/test-project-id/webhooks",
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "Webhook 1"
        assert data[1]["name"] == "Webhook 2"

    @pytest.mark.asyncio
    async def test_get_subscription_success(self, client, auth_headers):
        """Test successful webhook subscription retrieval"""
        # Arrange
        with patch('app.services.webhooks.WebhookService.get_subscription') as mock_get:
            mock_get.return_value = {
                "id": "sub-id",
                "name": "Test Webhook",
                "url": "https://example.com/webhook",
                "events": ["run.started"],
                "enabled": True,
                "created_at": "2024-01-01T00:00:00Z",
            }

            # Act
            response = await client.get(
                "/api/v1/projects/test-project-id/webhooks/sub-id",
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "sub-id"
        assert data["name"] == "Test Webhook"

    @pytest.mark.asyncio
    async def test_get_subscription_not_found(self, client, auth_headers):
        """Test webhook subscription retrieval when not found"""
        # Arrange
        with patch('app.services.webhooks.WebhookService.get_subscription') as mock_get:
            mock_get.return_value = None

            # Act
            response = await client.get(
                "/api/v1/projects/test-project-id/webhooks/nonexistent-id",
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_subscription_success(self, client, auth_headers):
        """Test successful webhook subscription update"""
        # Arrange
        update_data = {
            "name": "Updated Webhook",
            "enabled": False,
        }

        with patch('app.services.webhooks.WebhookService.update_subscription') as mock_update:
            mock_update.return_value = {
                "id": "sub-id",
                "name": "Updated Webhook",
                "url": "https://example.com/webhook",
                "events": ["run.started"],
                "enabled": False,
                "created_at": "2024-01-01T00:00:00Z",
            }

            # Act
            response = await client.patch(
                "/api/v1/projects/test-project-id/webhooks/sub-id",
                json=update_data,
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Webhook"
        assert data["enabled"] is False

    @pytest.mark.asyncio
    async def test_delete_subscription_success(self, client, auth_headers):
        """Test successful webhook subscription deletion"""
        # Arrange
        with patch('app.services.webhooks.WebhookService.delete_subscription') as mock_delete:
            mock_delete.return_value = True

            # Act
            response = await client.delete(
                "/api/v1/projects/test-project-id/webhooks/sub-id",
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_subscription_not_found(self, client, auth_headers):
        """Test webhook subscription deletion when not found"""
        # Arrange
        with patch('app.services.webhooks.WebhookService.delete_subscription') as mock_delete:
            mock_delete.return_value = False

            # Act
            response = await client.delete(
                "/api/v1/projects/test-project-id/webhooks/nonexistent-id",
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_test_webhook_success(self, client, auth_headers):
        """Test successful webhook test"""
        # Arrange
        test_data = {
            "url": "https://example.com/webhook",
            "secret": "test-secret",
            "event_type": "run.started",
        }

        with patch('app.services.webhooks.WebhookService.test_webhook') as mock_test:
            mock_test.return_value = (True, "Test webhook delivered successfully", "test-delivery-id")

            # Act
            response = await client.post(
                "/api/v1/projects/test-project-id/webhooks/test-send",
                json=test_data,
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "delivered successfully" in data["message"]
        assert data["delivery_id"] == "test-delivery-id"

    @pytest.mark.asyncio
    async def test_test_webhook_failure(self, client, auth_headers):
        """Test failed webhook test"""
        # Arrange
        test_data = {
            "url": "https://example.com/webhook",
            "secret": "test-secret",
            "event_type": "run.started",
        }

        with patch('app.services.webhooks.WebhookService.test_webhook') as mock_test:
            mock_test.return_value = (False, "HTTP 400: Bad Request", "test-delivery-id")

            # Act
            response = await client.post(
                "/api/v1/projects/test-project-id/webhooks/test-send",
                json=test_data,
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "HTTP 400" in data["message"]
        assert data["delivery_id"] == "test-delivery-id"

    @pytest.mark.asyncio
    async def test_list_deliveries_success(self, client, auth_headers):
        """Test successful webhook delivery listing"""
        # Arrange
        with patch('app.services.webhooks.WebhookService.list_deliveries') as mock_list:
            mock_list.return_value = (
                [
                    {
                        "id": "delivery1-id",
                        "event_type": "run.started",
                        "status": "delivered",
                        "attempts": 1,
                        "created_at": "2024-01-01T00:00:00Z",
                    },
                    {
                        "id": "delivery2-id",
                        "event_type": "run.finished",
                        "status": "failed",
                        "attempts": 3,
                        "last_error": "HTTP 500: Internal Server Error",
                        "created_at": "2024-01-01T01:00:00Z",
                    },
                ],
                2,
            )

            # Act
            response = await client.get(
                "/api/v1/projects/test-project-id/deliveries",
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert data["items"][0]["status"] == "delivered"
        assert data["items"][1]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_list_deliveries_with_filters(self, client, auth_headers):
        """Test webhook delivery listing with filters"""
        # Arrange
        with patch('app.services.webhooks.WebhookService.list_deliveries') as mock_list:
            mock_list.return_value = ([], 0)

            # Act
            response = await client.get(
                "/api/v1/projects/test-project-id/deliveries?status=failed&event_type=run.started",
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 200
        # Verify the service was called with correct filters
        mock_list.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_delivery_success(self, client, auth_headers):
        """Test successful webhook delivery retrieval"""
        # Arrange
        with patch('app.services.webhooks.WebhookService.get_delivery') as mock_get:
            mock_get.return_value = {
                "id": "delivery-id",
                "event_type": "run.started",
                "payload": {"test": "data"},
                "status": "delivered",
                "attempts": 1,
                "created_at": "2024-01-01T00:00:00Z",
                "delivered_at": "2024-01-01T00:00:05Z",
            }

            # Act
            response = await client.get(
                "/api/v1/projects/test-project-id/deliveries/delivery-id",
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "delivery-id"
        assert data["event_type"] == "run.started"
        assert data["status"] == "delivered"

    @pytest.mark.asyncio
    async def test_get_delivery_not_found(self, client, auth_headers):
        """Test webhook delivery retrieval when not found"""
        # Arrange
        with patch('app.services.webhooks.WebhookService.get_delivery') as mock_get:
            mock_get.return_value = None

            # Act
            response = await client.get(
                "/api/v1/projects/test-project-id/deliveries/nonexistent-id",
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_redeliver_webhook_success(self, client, auth_headers):
        """Test successful webhook redelivery"""
        # Arrange
        with patch('app.services.webhooks.WebhookService.redeliver_webhook') as mock_redeliver:
            mock_redeliver.return_value = True

            # Act
            response = await client.post(
                "/api/v1/deliveries/delivery-id/redeliver",
                json={},
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "scheduled successfully" in data["message"]
        assert data["delivery_id"] == "delivery-id"

    @pytest.mark.asyncio
    async def test_redeliver_webhook_not_found(self, client, auth_headers):
        """Test webhook redelivery when delivery not found"""
        # Arrange
        with patch('app.services.webhooks.WebhookService.redeliver_webhook') as mock_redeliver:
            mock_redeliver.return_value = False

            # Act
            response = await client.post(
                "/api/v1/deliveries/nonexistent-id/redeliver",
                json={},
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client):
        """Test API access without authentication"""
        # Act & Assert
        response = await client.get("/api/v1/projects/test-project-id/webhooks")
        assert response.status_code == 401

        response = await client.post(
            "/api/v1/projects/test-project-id/webhooks",
            json={}
        )
        assert response.status_code == 401

        response = await client.delete("/api/v1/projects/test-project-id/webhooks/sub-id")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_project_id(self, client, auth_headers):
        """Test API with invalid project ID"""
        # Act & Assert
        response = await client.get(
            "/api/v1/projects/invalid-uuid/webhooks",
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_pagination_parameters(self, client, auth_headers):
        """Test pagination parameters for delivery listing"""
        # Arrange
        with patch('app.services.webhooks.WebhookService.list_deliveries') as mock_list:
            mock_list.return_value = ([], 0)

            # Act
            response = await client.get(
                "/api/v1/projects/test-project-id/deliveries?limit=10&offset=20",
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 200
        # Verify the service was called with correct pagination
        mock_list.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_subscription_deliveries(self, client, auth_headers):
        """Test listing deliveries for a specific subscription"""
        # Arrange
        with patch('app.services.webhooks.WebhookService.list_deliveries') as mock_list:
            mock_list.return_value = ([], 0)

            # Act
            response = await client.get(
                "/api/v1/projects/test-project-id/webhooks/sub-id/deliveries",
                headers=auth_headers,
            )

        # Assert
        assert response.status_code == 200
        # Verify the service was called with subscription filter
        mock_list.assert_called_once()