# Use specific Python version with security updates
FROM python:3.13-alpine3.21

# Build arguments
ARG VERSION=dev

# Metadata
LABEL maintainer="tzockt" \
      description="Speedtest Exporter for Prometheus" \
      version="${VERSION}" \
      org.opencontainers.image.source="https://github.com/tzockt/speedtest-exporter"

# Speedtest CLI version
ARG SPEEDTEST_VERSION=1.2.0

# Security: Create non-root user early
RUN addgroup -g 1000 speedtest && \
    adduser -D -u 1000 -G speedtest speedtest

# Install system dependencies
RUN apk add --no-cache \
    ca-certificates \
    wget \
    curl \
    && rm -rf /var/cache/apk/*

# Set working directory
WORKDIR /app

# Copy requirements first for better layer caching
COPY src/requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip==24.3.1 && \
    pip install --no-cache-dir -r requirements.txt

# Install Speedtest CLI
RUN ARCHITECTURE=$(uname -m) && \
    case ${ARCHITECTURE} in \
        x86_64) SPEEDTEST_ARCH="x86_64" ;; \
        aarch64) SPEEDTEST_ARCH="aarch64" ;; \
        armv7l) SPEEDTEST_ARCH="armhf" ;; \
        armv6l) SPEEDTEST_ARCH="armel" ;; \
        *) echo "Unsupported architecture: ${ARCHITECTURE}" && exit 1 ;; \
    esac && \
    wget -q -O /tmp/speedtest.tgz \
        "https://install.speedtest.net/app/cli/ookla-speedtest-${SPEEDTEST_VERSION}-linux-${SPEEDTEST_ARCH}.tgz" && \
    tar -xzf /tmp/speedtest.tgz -C /tmp && \
    install -m 755 /tmp/speedtest /usr/local/bin/speedtest && \
    rm -rf /tmp/*

# Copy application code
COPY src/ ./

# Change ownership and switch to non-root user
RUN chown -R speedtest:speedtest /app
USER speedtest

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${SPEEDTEST_PORT:-9798}/health || exit 1

# Expose port
EXPOSE 9798

# Set default environment variables
ENV SPEEDTEST_PORT=9798 \
    SPEEDTEST_CACHE_DURATION=0 \
    SPEEDTEST_TIMEOUT=90 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Run the application
CMD ["python", "-u", "exporter.py"]