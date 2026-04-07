"""Tests for the speedtest exporter."""

import json
import subprocess
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, call

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import exporter
from exporter import (
    SpeedtestError,
    bits_to_megabits,
    bytes_to_bits,
    get_metrics,
    run_speedtest,
    update_prometheus_metrics,
    validate_speedtest_binary,
    app,
)

# Sample valid speedtest JSON output
VALID_SPEEDTEST_JSON = {
    "type": "result",
    "server": {"id": 12345},
    "ping": {"latency": 10.5, "jitter": 1.2},
    "download": {"bandwidth": 12500000},
    "upload": {"bandwidth": 6250000},
}

VALID_METRICS = {
    "server_id": 12345,
    "jitter": 1.2,
    "ping": 10.5,
    "download": bytes_to_bits(12500000),
    "upload": bytes_to_bits(6250000),
    "up": 1,
}


class TestUtilityFunctions:
    """Test utility functions."""

    def test_bytes_to_bits(self):
        assert bytes_to_bits(1) == 8
        assert bytes_to_bits(0) == 0
        assert bytes_to_bits(1.5) == 12.0

    def test_bits_to_megabits(self):
        assert bits_to_megabits(1_000_000) == 1.0
        assert bits_to_megabits(0) == 0.0
        assert bits_to_megabits(500_000) == 0.5
        assert bits_to_megabits(1_500_000) == 1.5


class TestSpeedtestError:
    """Test custom exception."""

    def test_speedtest_error_creation(self):
        error = SpeedtestError("Test error")
        assert str(error) == "Test error"

    def test_speedtest_error_is_exception(self):
        assert issubclass(SpeedtestError, Exception)


class TestValidateSpeedtestBinary:
    """Test speedtest binary validation."""

    @patch("exporter.which")
    @patch("exporter.subprocess.run")
    def test_valid_official_binary(self, mock_run, mock_which):
        mock_which.return_value = "/usr/local/bin/speedtest"
        mock_run.return_value = Mock(stdout="Speedtest by Ookla 1.2.0\n", returncode=0)
        validate_speedtest_binary()  # should not raise

    @patch("exporter.which")
    def test_binary_not_found_exits(self, mock_which):
        mock_which.return_value = None
        with pytest.raises(SystemExit) as exc:
            validate_speedtest_binary()
        assert exc.value.code == 1

    @patch("exporter.which")
    @patch("exporter.subprocess.run")
    def test_non_official_binary_exits(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/speedtest"
        mock_run.return_value = Mock(stdout="speedtest-cli 2.1.3\n", returncode=0)
        with pytest.raises(SystemExit) as exc:
            validate_speedtest_binary()
        assert exc.value.code == 1

    @patch("exporter.which")
    @patch("exporter.subprocess.run")
    def test_timeout_exits(self, mock_run, mock_which):
        mock_which.return_value = "/usr/local/bin/speedtest"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="speedtest", timeout=10)
        with pytest.raises(SystemExit) as exc:
            validate_speedtest_binary()
        assert exc.value.code == 1

    @patch("exporter.which")
    @patch("exporter.subprocess.run")
    def test_called_process_error_exits(self, mock_run, mock_which):
        mock_which.return_value = "/usr/local/bin/speedtest"
        mock_run.side_effect = subprocess.CalledProcessError(1, "speedtest")
        with pytest.raises(SystemExit) as exc:
            validate_speedtest_binary()
        assert exc.value.code == 1


class TestRunSpeedtest:
    """Test the run_speedtest function."""

    @patch("exporter.subprocess.run")
    def test_success_returns_correct_metrics(self, mock_run):
        mock_run.return_value = Mock(
            stdout=json.dumps(VALID_SPEEDTEST_JSON), returncode=0
        )
        result = run_speedtest()
        assert result["server_id"] == 12345
        assert result["ping"] == 10.5
        assert result["jitter"] == 1.2
        assert result["download"] == bytes_to_bits(12500000)
        assert result["upload"] == bytes_to_bits(6250000)
        assert result["up"] == 1

    @patch("exporter.subprocess.run")
    def test_timeout_raises_speedtest_error(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="speedtest", timeout=90)
        with pytest.raises(SpeedtestError, match="timeout"):
            run_speedtest()

    @patch("exporter.subprocess.run")
    def test_process_error_raises_speedtest_error(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "speedtest", output=""
        )
        with pytest.raises(SpeedtestError):
            run_speedtest()

    @patch("exporter.subprocess.run")
    def test_process_error_with_json_error_message(self, mock_run):
        error_output = json.dumps({"error": "No servers available"})
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "speedtest", output=error_output
        )
        with pytest.raises(SpeedtestError, match="No servers available"):
            run_speedtest()

    @patch("exporter.subprocess.run")
    def test_invalid_json_raises_speedtest_error(self, mock_run):
        mock_run.return_value = Mock(stdout="not valid json", returncode=0)
        with pytest.raises(SpeedtestError, match="Invalid JSON"):
            run_speedtest()

    @patch("exporter.subprocess.run")
    def test_error_field_in_result_raises(self, mock_run):
        mock_run.return_value = Mock(
            stdout=json.dumps({"error": "Connection failed"}), returncode=0
        )
        with pytest.raises(SpeedtestError, match="Connection failed"):
            run_speedtest()

    @patch("exporter.subprocess.run")
    def test_unexpected_result_type_raises(self, mock_run):
        mock_run.return_value = Mock(
            stdout=json.dumps({"type": "log", "message": "test"}), returncode=0
        )
        with pytest.raises(SpeedtestError, match="Unexpected"):
            run_speedtest()

    @patch("exporter.SERVER_ID", "67890")
    @patch("exporter.subprocess.run")
    def test_server_id_included_in_command(self, mock_run):
        mock_run.return_value = Mock(
            stdout=json.dumps(VALID_SPEEDTEST_JSON), returncode=0
        )
        run_speedtest()
        cmd = mock_run.call_args[0][0]
        assert "--server-id" in cmd
        assert "67890" in cmd

    @patch("exporter.SERVER_ID", None)
    @patch("exporter.subprocess.run")
    def test_no_server_id_not_in_command(self, mock_run):
        mock_run.return_value = Mock(
            stdout=json.dumps(VALID_SPEEDTEST_JSON), returncode=0
        )
        run_speedtest()
        cmd = mock_run.call_args[0][0]
        assert "--server-id" not in cmd


class TestGetMetrics:
    """Test the get_metrics function with caching logic."""

    def setup_method(self):
        """Reset global cache state before each test."""
        exporter.cached_metrics = None
        exporter.last_test_time = datetime.min

    @patch("exporter.run_speedtest")
    def test_no_cache_runs_speedtest(self, mock_run):
        mock_run.return_value = VALID_METRICS.copy()
        result = get_metrics()
        mock_run.assert_called_once()
        assert result == VALID_METRICS

    @patch("exporter.CACHE_DURATION", 300)
    @patch("exporter.run_speedtest")
    def test_valid_cache_skips_speedtest(self, mock_run):
        exporter.cached_metrics = VALID_METRICS.copy()
        exporter.last_test_time = datetime.now()
        result = get_metrics()
        mock_run.assert_not_called()
        assert result == VALID_METRICS

    @patch("exporter.CACHE_DURATION", 300)
    @patch("exporter.run_speedtest")
    def test_expired_cache_reruns_speedtest(self, mock_run):
        fresh_metrics = VALID_METRICS.copy()
        fresh_metrics["server_id"] = 99999
        mock_run.return_value = fresh_metrics
        exporter.cached_metrics = VALID_METRICS.copy()
        exporter.last_test_time = datetime.now() - timedelta(seconds=400)
        result = get_metrics()
        mock_run.assert_called_once()
        assert result["server_id"] == 99999

    @patch("exporter.CACHE_DURATION", 0)
    @patch("exporter.run_speedtest")
    def test_cache_duration_zero_always_reruns(self, mock_run):
        mock_run.return_value = VALID_METRICS.copy()
        exporter.cached_metrics = VALID_METRICS.copy()
        exporter.last_test_time = datetime.now()
        get_metrics()
        mock_run.assert_called_once()

    @patch("exporter.run_speedtest")
    def test_speedtest_failure_returns_zeros(self, mock_run):
        mock_run.side_effect = SpeedtestError("Connection failed")
        result = get_metrics()
        assert result["up"] == 0
        assert result["download"] == 0
        assert result["upload"] == 0
        assert result["ping"] == 0
        assert result["server_id"] == 0


class TestUpdatePrometheusMetrics:
    """Test that Prometheus gauges are updated correctly."""

    def test_sets_all_gauges(self):
        metrics = {
            "server_id": 42,
            "jitter": 1.5,
            "ping": 12.3,
            "download": 100_000_000.0,
            "upload": 50_000_000.0,
            "up": 1,
        }
        with (
            patch.object(exporter.speedtest_server_id, "set") as mock_sid,
            patch.object(exporter.speedtest_jitter, "set") as mock_jitter,
            patch.object(exporter.speedtest_ping, "set") as mock_ping,
            patch.object(exporter.speedtest_download, "set") as mock_dl,
            patch.object(exporter.speedtest_upload, "set") as mock_ul,
            patch.object(exporter.speedtest_up, "set") as mock_up,
        ):
            update_prometheus_metrics(metrics)
            mock_sid.assert_called_once_with(42)
            mock_jitter.assert_called_once_with(1.5)
            mock_ping.assert_called_once_with(12.3)
            mock_dl.assert_called_once_with(100_000_000.0)
            mock_ul.assert_called_once_with(50_000_000.0)
            mock_up.assert_called_once_with(1)

    def test_sets_failure_metrics(self):
        metrics = {
            "server_id": 0,
            "jitter": 0,
            "ping": 0,
            "download": 0,
            "upload": 0,
            "up": 0,
        }
        with patch.object(exporter.speedtest_up, "set") as mock_up:
            update_prometheus_metrics(metrics)
            mock_up.assert_called_once_with(0)


class TestFlaskApp:
    """Test Flask application endpoints."""

    @patch("exporter.subprocess.run")
    def test_health_endpoint_success(self, mock_run):
        mock_run.return_value = Mock(returncode=0)
        with app.test_client() as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.data == b"OK"

    @patch("exporter.subprocess.run")
    def test_health_endpoint_binary_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        with app.test_client() as client:
            response = client.get("/health")
            assert response.status_code == 500
            assert response.data == b"ERROR"

    @patch("exporter.subprocess.run")
    def test_health_endpoint_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="speedtest", timeout=5)
        with app.test_client() as client:
            response = client.get("/health")
            assert response.status_code == 500

    def test_index_endpoint_returns_html(self):
        with app.test_client() as client:
            response = client.get("/")
            assert response.status_code == 200
            assert b"Speedtest Exporter" in response.data
            assert b"<html>" in response.data
            assert b"/metrics" in response.data
            assert b"/health" in response.data

    @patch("exporter.get_metrics")
    def test_metrics_endpoint_success(self, mock_get_metrics):
        mock_get_metrics.return_value = VALID_METRICS.copy()
        with app.test_client() as client:
            response = client.get("/metrics")
            assert response.status_code == 200
            assert b"speedtest_up" in response.data

    @patch("exporter.get_metrics")
    def test_metrics_endpoint_unexpected_error_returns_500(self, mock_get_metrics):
        mock_get_metrics.side_effect = RuntimeError("Unexpected failure")
        with app.test_client() as client:
            response = client.get("/metrics")
            assert response.status_code == 500
