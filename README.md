# Speedtest Exporter

[![CI](https://github.com/tzockt/speedtest-exporter/actions/workflows/ci.yml/badge.svg)](https://github.com/tzockt/speedtest-exporter/actions/workflows/ci.yml)
[![Release](https://github.com/tzockt/speedtest-exporter/actions/workflows/release.yml/badge.svg)](https://github.com/tzockt/speedtest-exporter/actions/workflows/release.yml)
[![Docker Pulls](https://img.shields.io/docker/pulls/ghcr.io/tzockt/speedtest-exporter)](https://github.com/tzockt/speedtest-exporter/pkgs/container/speedtest-exporter)

A modern **Prometheus exporter** for **Ookla Speedtest CLI** written in **Python**. This exporter runs internet speed tests and exposes the results as Prometheus metrics.

## Features

- 🚀 **Modern Python 3.11+ codebase** with type hints and async support
- 📊 **Prometheus metrics** for download/upload speeds, ping, jitter, and server info
- 🐳 **Multi-architecture Docker images** (amd64, arm64, armv7)
- 🔒 **Security-focused** with non-root containers and minimal attack surface
- ⚡ **Configurable caching** to avoid excessive speed tests
- 🏥 **Health checks** and proper error handling
- 📝 **Comprehensive logging** with structured output

## Quick Start

### Docker (Recommended)

```bash
docker run -d \
  --name speedtest-exporter \
  -p 9798:9798 \
  ghcr.io/tzockt/speedtest-exporter:latest
```

### Docker Compose

```yaml
version: '3.8'
services:
  speedtest-exporter:
    image: ghcr.io/tzockt/speedtest-exporter:latest
    ports:
      - "9798:9798"
    environment:
      - SPEEDTEST_CACHE_DURATION=300  # Cache results for 5 minutes
      - SPEEDTEST_TIMEOUT=90
    restart: unless-stopped
```

### Python

```bash
# Install dependencies
pip install -r src/requirements.txt

# Run the exporter
cd src && python exporter.py
```

## Configuration

The exporter can be configured using environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `SPEEDTEST_PORT` | Port to listen on | `9798` |
| `SPEEDTEST_CACHE_DURATION` | Cache duration in seconds (0 = no cache) | `0` |
| `SPEEDTEST_TIMEOUT` | Speedtest timeout in seconds | `90` |
| `SPEEDTEST_SERVER_ID` | Specific server ID to use | Auto-select |

## Metrics

The exporter provides the following Prometheus metrics:

| Metric | Description | Unit |
|--------|-------------|------|
| `speedtest_download_bits_per_second` | Download speed | bits/second |
| `speedtest_upload_bits_per_second` | Upload speed | bits/second |
| `speedtest_ping_latency_milliseconds` | Ping latency | milliseconds |
| `speedtest_jitter_latency_milliseconds` | Jitter latency | milliseconds |
| `speedtest_server_id` | Server ID used for test | - |
| `speedtest_up` | Test success status (1=success, 0=failure) | - |

## Endpoints

- `/` - Web interface with links to metrics and health check
- `/metrics` - Prometheus metrics endpoint
- `/health` - Health check endpoint

## Prometheus Configuration

Add this to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'speedtest'
    static_configs:
      - targets: ['speedtest-exporter:9798']
    scrape_interval: 5m  # Don't scrape too frequently
    scrape_timeout: 2m
```

## Development

### Requirements

- Python 3.11+
- Docker (for containerized development)

### Setup

```bash
# Clone the repository
git clone https://github.com/tzockt/speedtest-exporter.git
cd speedtest-exporter

# Install development dependencies
pip install -r src/requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Run tests
pytest

# Run linting
ruff check src/
black --check src/
mypy src/
```

### Building

```bash
# Build Docker image
docker build -t speedtest-exporter .

# Run locally
docker run -p 9798:9798 speedtest-exporter
```

### Releasing a New Version

The project uses a single source of truth for versioning. To release a new version:

1. **Update the version** in `pyproject.toml`:
   ```toml
   version = "2.0.2"
   ```

2. **Commit and push** the change:
   ```bash
   git add pyproject.toml
   git commit -m "chore: bump version to 2.0.2"
   git push
   ```

3. **Create and push a git tag**:
   ```bash
   git tag v2.0.2
   git push origin v2.0.2
   ```

This will automatically trigger the release workflow which:
- Builds multi-architecture Docker images
- Tags them with the version (e.g., `2.0.2`, `2.0`, `2`, `latest`)
- Generates an SBOM (Software Bill of Materials)
- Creates a GitHub Release with auto-generated changelog

## Architecture Support

The Docker images support multiple architectures:

- `linux/amd64` (Intel/AMD 64-bit)
- `linux/arm64` (ARM 64-bit, e.g., Raspberry Pi 4, Apple Silicon)
- `linux/arm/v7` (ARM 32-bit, e.g., Raspberry Pi 3)

## Security

- Runs as non-root user (UID 1000)
- Minimal Alpine Linux base image
- Regular security updates via Dependabot
- SBOM (Software Bill of Materials) generation

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

This is a modernized fork of [miguelndecarvalho/speedtest-exporter](https://github.com/miguelndecarvalho/speedtest-exporter).

Special thanks to:
- [Miguel N. de Carvalho](https://github.com/miguelndecarvalho) – Author of the original project
- [Ookla](https://www.speedtest.net/) – For providing the excellent Speedtest CLI