FROM python:3.13.7-alpine3.21

# Speedtest CLI Version
ARG SPEEDTEST_VERSION=1.2.0

# Create user
RUN adduser -D speedtest

WORKDIR /app
COPY src/requirements.txt .

# Install required modules and Speedtest CLI
RUN pip install --no-cache-dir -r requirements.txt && \
    ARCHITECTURE=$(uname -m) && \
    export ARCHITECTURE && \
    if [ "$ARCHITECTURE" = 'armv7l' ];then ARCHITECTURE="armhf";fi && \
    wget -nv -O /tmp/speedtest.tgz "https://install.speedtest.net/app/cli/ookla-speedtest-${SPEEDTEST_VERSION}-linux-${ARCHITECTURE}.tgz" && \
    tar zxvf /tmp/speedtest.tgz -C /tmp && \
    cp /tmp/speedtest /usr/local/bin && \
    chmod +x /usr/local/bin/speedtest && \
    chown -R speedtest:speedtest /app && \
    rm -rf \
     /tmp/* \
     /app/requirements

COPY src/. .

USER speedtest

CMD ["python", "-u", "exporter.py"]

HEALTHCHECK --timeout=10s CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:${SPEEDTEST_PORT:=9798}/
