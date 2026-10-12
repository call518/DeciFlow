FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.7.20 /uv /usr/local/bin/uv

ENV DEBIAN_FRONTEND=noninteractive

# 서비스 자동 기동 차단 정책 적용 후 패키지 설치, 정책 파일 제거
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
 && chmod +x /usr/sbin/policy-rc.d \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      tcpdump \
      net-tools \
      dnsutils \
      wget \
      curl \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/* /usr/sbin/policy-rc.d

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/deciflow-venv \
    DECIFLOW_DATA_DIR=/var/lib/deciflow-data \
    PYTHONUNBUFFERED=1
RUN mkdir -p /var/lib/deciflow-data/actions /var/lib/deciflow-data/criteria
EXPOSE 4000
CMD ["sh", "-c", "uv sync --frozen --no-dev --no-install-project --no-cache && exec /opt/deciflow-venv/bin/python -c \"import server; server.main(host='0.0.0.0')\""]
