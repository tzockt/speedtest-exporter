"""Tests for the speedtest exporter."""

import pytest
from unittest.mock import Mock, patch
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from exporter import bytes_to_bits, bits_to_megabits, SpeedtestError


class TestUtilityFunctions:
    """Test utility functions."""

    def test_bytes_to_bits(self):
        """Test bytes to bits conversion."""
        assert bytes_to_bits(1) == 8
        assert bytes_to_bits(0) == 0
        assert bytes_to_bits(1.5) == 12.0

    def test_bits_to_megabits(self):
        """Test bits to megabits conversion."""
        assert bits_to_megabits(1_000_000) == 1.0
        assert bits_to_megabits(0) == 0.0
        assert bits_to_megabits(500_000) == 0.5


class TestSpeedtestError:
    """Test custom exception."""

    def test_speedtest_error_creation(self):
        """Test SpeedtestError can be created."""
        error = SpeedtestError("Test error")
        assert str(error) == "Test error"


class TestFlaskApp:
    """Test Flask application."""

    @patch('exporter.subprocess.run')
    def test_health_endpoint_success(self, mock_run):
        """Test health endpoint returns OK when speedtest binary is accessible."""
        from exporter import app
        
        # Mock successful speedtest binary check
        mock_run.return_value = Mock(returncode=0)
        
        with app.test_client() as client:
            response = client.get('/health')
            assert response.status_code == 200
            assert response.data == b'OK'

    @patch('exporter.subprocess.run')
    def test_health_endpoint_failure(self, mock_run):
        """Test health endpoint returns ERROR when speedtest binary fails."""
        from exporter import app
        
        # Mock failed speedtest binary check
        mock_run.side_effect = FileNotFoundError()
        
        with app.test_client() as client:
            response = client.get('/health')
            assert response.status_code == 500
            assert response.data == b'ERROR'

    def test_index_endpoint(self):
        """Test index endpoint returns HTML."""
        from exporter import app
        
        with app.test_client() as client:
            response = client.get('/')
            assert response.status_code == 200
            assert b'Speedtest Exporter' in response.data
            assert b'<html>' in response.data