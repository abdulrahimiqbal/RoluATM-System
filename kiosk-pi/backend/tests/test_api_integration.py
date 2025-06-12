"""
Integration tests for RoluATM Kiosk Backend API

Tests the complete Flask application with mocked hardware and cloud API.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from tflex_driver import TFlexStatus, TFlexException


@pytest.fixture
def app():
    """Create test Flask application"""
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def mock_tflex():
    """Mock T-Flex driver"""
    with patch('app.tflex_driver') as mock_driver:
        mock_driver.is_connected.return_value = True
        mock_driver.get_status.return_value = TFlexStatus.READY
        mock_driver.get_coin_count.return_value = 100
        mock_driver.dispense_coins.return_value = True
        yield mock_driver


@pytest.fixture
def mock_cloud_api():
    """Mock cloud API responses"""
    with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
        # Mock health check response
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"status": "healthy"}
        
        # Mock cloud API responses
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"success": True}
        
        yield mock_get, mock_post


class TestHealthEndpoint:
    """Test health check endpoint"""
    
    def test_health_check_healthy(self, client, mock_tflex, mock_cloud_api):
        """Test health check when everything is healthy"""
        response = client.get('/api/health')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['kiosk_id'] is not None
        assert data['hardware']['tflex_connected'] is True
        assert data['cloud']['status'] == 'online'
    
    def test_health_check_hardware_error(self, client, mock_cloud_api):
        """Test health check with hardware error"""
        with patch('app.tflex_driver') as mock_driver:
            mock_driver.is_connected.return_value = False
            
            response = client.get('/api/health')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['hardware']['tflex_connected'] is False


class TestBalanceEndpoint:
    """Test balance endpoint"""
    
    def test_get_balance_success(self, client, mock_tflex):
        """Test successful balance retrieval"""
        response = client.get('/api/balance')
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert 'coin_count' in data
        assert 'status' in data
        assert data['coin_count'] == 100
    
    def test_get_balance_hardware_error(self, client):
        """Test balance with hardware error"""
        with patch('app.tflex_driver') as mock_driver:
            mock_driver.get_coin_count.side_effect = TFlexException("Hardware error")
            
            response = client.get('/api/balance')
            
            assert response.status_code == 500
            data = json.loads(response.data)
            assert 'error' in data


class TestWithdrawEndpoint:
    """Test withdrawal endpoint"""
    
    def test_withdraw_success(self, client, mock_tflex, mock_cloud_api):
        """Test successful withdrawal"""
        request_data = {
            'amount_usd': 5.0,
            'session_id': 'test_session_123'
        }
        
        response = client.post(
            '/api/withdraw',
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        
        assert data['success'] is True
        assert 'transaction_id' in data
    
    def test_withdraw_invalid_amount(self, client, mock_tflex, mock_cloud_api):
        """Test withdrawal with invalid amount"""
        request_data = {
            'amount_usd': 0,  # Invalid amount
            'session_id': 'test_session_123'
        }
        
        response = client.post(
            '/api/withdraw',
            data=json.dumps(request_data),
            content_type='application/json'
        )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_withdraw_cloud_offline(self, client, mock_tflex):
        """Test withdrawal when cloud is offline"""
        with patch('app.check_cloud_connectivity') as mock_check:
            mock_check.return_value = False
            
            request_data = {
                'amount_usd': 5.0,
                'session_id': 'test_session_123'
            }
            
            response = client.post(
                '/api/withdraw',
                data=json.dumps(request_data),
                content_type='application/json'
            )
            
            assert response.status_code == 503
            data = json.loads(response.data)
            assert 'cloud service unavailable' in data['error'].lower()


class TestMetricsEndpoint:
    """Test Prometheus metrics endpoint"""
    
    def test_metrics_endpoint(self, client):
        """Test metrics endpoint returns Prometheus format"""
        response = client.get('/metrics')
        
        assert response.status_code == 200
        assert 'text/plain' in response.content_type
        
        # Check for expected metrics
        metrics_text = response.data.decode('utf-8')
        assert 'roluatm_requests_total' in metrics_text
        assert 'roluatm_hardware_status' in metrics_text
        assert 'roluatm_cloud_status' in metrics_text


class TestErrorHandling:
    """Test error handling scenarios"""
    
    def test_404_for_unknown_endpoint(self, client):
        """Test 404 for unknown endpoints"""
        response = client.get('/api/unknown')
        assert response.status_code == 404
    
    def test_method_not_allowed(self, client):
        """Test 405 for wrong HTTP methods"""
        response = client.post('/api/health')
        assert response.status_code == 405
    
    def test_invalid_json(self, client):
        """Test handling of invalid JSON"""
        response = client.post(
            '/api/withdraw',
            data='invalid json',
            content_type='application/json'
        )
        assert response.status_code == 400


if __name__ == '__main__':
    pytest.main([__file__]) 