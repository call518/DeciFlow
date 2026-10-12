FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.7.20 /uv /usr/local/bin/uv

ENV DEBIAN_FRONTEND=noninteractive

# 서비스 자동 기동 차단 정책 적용 후 패키지 설치, 정책 파일 제거
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
 && chmod +x /usr/sbin/policy-rc.d \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      tcpdump \
      net-tools \
      dnsutils \
      wget \
      curl \
      tree \
      watch \
      vim \
 && rm -rf /var/lib/apt/lists/* /usr/sbin/policy-rc.d \
 && printf "%s\n" \
      "alias cp='cp -i'" \
      "alias dmesg='\dmesg --color=auto --reltime --human --nopager --decode'" \
      "alias egrep='egrep --color=auto'" \
      "alias fgrep='fgrep --color=auto'" \
      "alias free='\free -mht'" \
      "alias grep='\grep --color=auto'" \
      "alias l.='ls -d .* --color=auto'" \
      "alias ll='ls -al --color=auto'" \
      "alias ls='ls --color=auto'" \
      "alias mv='mv -i'" \
      "alias nvitop='uvx nvitop'" \
      "alias pacman='\pacman --color=auto'" \
      "alias rm='rm -i'" \
      "alias sudo='\sudo '" \
      "alias tree='\tree --dirsfirst -C'" \
      "alias txtcolor='curl -s https://gist.githubusercontent.com/HaleTom/89ffe32783f89f403bba96bd7bcd1263/raw/ | bash'" \
      "alias uvsrc='source .venv/bin/activate'" \
      "alias vi='vim'" \
      "alias xzegrep='xzegrep --color=auto'" \
      "alias xzfgrep='xzfgrep --color=auto'" \
      "alias xzgrep='xzgrep --color=auto'" \
      "alias zegrep='zegrep --color=auto'" \
      "alias zfgrep='zfgrep --color=auto'" \
      "alias zgrep='zgrep --color=auto'" \
      >> /root/.bashrc

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/deciflow-venv \
    DECIFLOW_DATA_DIR=/var/lib/deciflow-data \
    PYTHONUNBUFFERED=1
RUN mkdir -p /var/lib/deciflow-data/actions /var/lib/deciflow-data/criteria
EXPOSE 4000
CMD ["sh", "-c", "uv sync --frozen --no-dev --no-install-project --no-cache && exec /opt/deciflow-venv/bin/python -c \"import server; server.main(host='0.0.0.0')\""]
