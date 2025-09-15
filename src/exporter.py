#!/usr/bin/env python3
"""
Speedtest Exporter for Prometheus

A modern Prometheus exporter that runs Ookla's Speedtest CLI and exposes metrics.
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from shutil import which
from typing import cast

from flask import Flask, Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from waitress import serve

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Disable waitress logs
logging.getLogger("waitress").setLevel(logging.WARNING)

# Flask app
app = Flask(__name__)

# Prometheus metrics
speedtest_server_id = Gauge(
    "speedtest_server_id", "Speedtest server ID used for testing"
)
speedtest_jitter = Gauge(
    "speedtest_jitter_latency_milliseconds", "Speedtest jitter in milliseconds"
)
speedtest_ping = Gauge(
    "speedtest_ping_latency_milliseconds", "Speedtest ping latency in milliseconds"
)
speedtest_download = Gauge(
    "speedtest_download_bits_per_second", "Speedtest download speed in bits per second"
)
speedtest_upload = Gauge(
    "speedtest_upload_bits_per_second", "Speedtest upload speed in bits per second"
)
speedtest_up = Gauge("speedtest_up", "Speedtest status - 1 if successful, 0 if failed")

# Configuration
CACHE_DURATION = int(os.environ.get("SPEEDTEST_CACHE_DURATION", "0"))
SERVER_ID = os.environ.get("SPEEDTEST_SERVER_ID")
TIMEOUT = int(os.environ.get("SPEEDTEST_TIMEOUT", "90"))
PORT = int(os.environ.get("SPEEDTEST_PORT", "9798"))

# Cache
last_test_time = datetime.min
cached_metrics: dict[str, int | float] | None = None


class SpeedtestError(Exception):
    """Custom exception for speedtest errors."""

    pass


def bytes_to_bits(bytes_per_sec: int | float) -> float:
    """Convert bytes per second to bits per second."""
    return float(bytes_per_sec) * 8


def bits_to_megabits(bits_per_sec: int | float) -> float:
    """Convert bits per second to megabits per second."""
    return round(float(bits_per_sec) * 1e-6, 2)


def validate_speedtest_binary() -> None:
    """Validate that the official Speedtest CLI is installed and accessible."""
    if not which("speedtest"):
        logger.error(
            "Speedtest CLI not found. Please install from: "
            "https://www.speedtest.net/apps/cli"
        )
        sys.exit(1)

    try:
        result = subprocess.run(
            ["speedtest", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )

        if "Speedtest by Ookla" not in result.stdout:
            logger.error(
                "Non-official Speedtest CLI detected. Please install the official "
                "version from: https://www.speedtest.net/apps/cli"
            )
            sys.exit(1)

        logger.info(f"Speedtest CLI validated: {result.stdout.strip()}")

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
        logger.error(f"Failed to validate Speedtest CLI: {e}")
        sys.exit(1)


def run_speedtest() -> dict[str, int | float]:
    """
    Run speedtest and return metrics.

    Returns:
        Dictionary containing speedtest metrics

    Raises:
        SpeedtestError: If speedtest fails or returns invalid data
    """
    cmd = [
        "speedtest",
        "--format=json-pretty",
        "--progress=no",
        "--accept-license",
        "--accept-gdpr",
    ]

    if SERVER_ID:
        cmd.extend(["--server-id", SERVER_ID])

    logger.info(f"Running speedtest with command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT, check=True
        )

        data = json.loads(result.stdout)

        if "error" in data:
            raise SpeedtestError(f"Speedtest error: {data['error']}")

        if data.get("type") != "result":
            raise SpeedtestError(
                f"Unexpected speedtest output type: {data.get('type')}"
            )

        # Extract metrics
        metrics = {
            "server_id": int(data["server"]["id"]),
            "jitter": float(data["ping"]["jitter"]),
            "ping": float(data["ping"]["latency"]),
            "download": bytes_to_bits(data["download"]["bandwidth"]),
            "upload": bytes_to_bits(data["upload"]["bandwidth"]),
            "up": 1,
        }

        logger.info(
            f"Speedtest completed - Server: {metrics['server_id']}, "
            f"Ping: {metrics['ping']:.2f}ms, "
            f"Jitter: {metrics['jitter']:.2f}ms, "
            f"Download: {bits_to_megabits(metrics['download']):.2f}Mbps, "
            f"Upload: {bits_to_megabits(metrics['upload']):.2f}Mbps"
        )

        return metrics

    except subprocess.TimeoutExpired as e:
        logger.error(f"Speedtest timed out after {TIMEOUT} seconds")
        raise SpeedtestError("Speedtest timeout") from e

    except subprocess.CalledProcessError as e:
        logger.error(f"Speedtest command failed: {e}")
        if e.stdout:
            try:
                error_data = json.loads(e.stdout)
                if "error" in error_data:
                    raise SpeedtestError(f"Speedtest error: {error_data['error']}")
            except json.JSONDecodeError:
                pass
        raise SpeedtestError("Speedtest command failed") from e

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse speedtest JSON output: {e}")
        raise SpeedtestError("Invalid JSON output from speedtest") from e


def get_metrics() -> dict[str, int | float]:
    """
    Get speedtest metrics, using cache if available and valid.

    Returns:
        Dictionary containing speedtest metrics
    """
    global last_test_time, cached_metrics

    now = datetime.now()
    cache_valid = (
        CACHE_DURATION > 0
        and cached_metrics is not None
        and (now - last_test_time).total_seconds() < CACHE_DURATION
    )

    if cache_valid:
        logger.debug("Using cached metrics")
        return cast(dict[str, int | float], cached_metrics)

    try:
        metrics = run_speedtest()
        cached_metrics = metrics
        last_test_time = now
        return metrics

    except SpeedtestError as e:
        logger.error(f"Speedtest failed: {e}")
        return {
            "server_id": 0,
            "jitter": 0,
            "ping": 0,
            "download": 0,
            "upload": 0,
            "up": 0,
        }


def update_prometheus_metrics(metrics: dict[str, int | float]) -> None:
    """Update Prometheus metrics with speedtest results."""
    speedtest_server_id.set(metrics["server_id"])
    speedtest_jitter.set(metrics["jitter"])
    speedtest_ping.set(metrics["ping"])
    speedtest_download.set(metrics["download"])
    speedtest_upload.set(metrics["upload"])
    speedtest_up.set(metrics["up"])


@app.route("/")
def index() -> str:
    """Health check and info endpoint."""
    return """
    <html>
        <head><title>Speedtest Exporter</title></head>
        <body>
            <h1>Speedtest Exporter</h1>
            <p>Prometheus exporter for Ookla Speedtest CLI</p>
            <p><a href="/metrics">Metrics</a></p>
            <p><a href="/health">Health Check</a></p>
        </body>
    </html>
    """


@app.route("/health")
def health() -> tuple[str, int]:
    """Health check endpoint."""
    try:
        # Quick validation that speedtest binary is accessible
        subprocess.run(
            ["speedtest", "--version"], capture_output=True, timeout=5, check=True
        )
        return "OK", 200
    except (
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
        FileNotFoundError,
    ):
        return "ERROR", 500


@app.route("/metrics")
def metrics() -> Response:
    """Prometheus metrics endpoint."""
    try:
        metrics_data = get_metrics()
        update_prometheus_metrics(metrics_data)

        # Generate Prometheus format
        output = generate_latest()
        return Response(output, mimetype=CONTENT_TYPE_LATEST)

    except Exception as e:
        logger.error(f"Error generating metrics: {e}")
        # Return empty metrics on error
        return Response("", mimetype=CONTENT_TYPE_LATEST, status=500)


def main() -> None:
    """Main application entry point."""
    logger.info("Starting Speedtest Exporter")

    # Log configuration
    logger.info("Configuration:")
    logger.info(f"  Port: {PORT}")
    logger.info(f"  Cache Duration: {CACHE_DURATION}s")
    logger.info(f"  Timeout: {TIMEOUT}s")
    logger.info(f"  Server ID: {SERVER_ID or 'Auto'}")

    # Validate speedtest binary
    validate_speedtest_binary()

    # Start server
    logger.info(f"Starting server on http://0.0.0.0:{PORT}")
    serve(
        app,
        host="0.0.0.0",
        port=PORT,
        threads=4,
        cleanup_interval=30,
        channel_timeout=120,
    )


if __name__ == "__main__":
    main()
