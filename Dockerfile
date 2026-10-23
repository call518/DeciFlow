FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.7.20 /uv /usr/local/bin/uv

ENV DEBIAN_FRONTEND=noninteractive

# 서비스 자동 기동 차단 정책 적용 후 패키지 설치, 정책 파일 제거
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d \
 && chmod +x /usr/sbin/policy-rc.d \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      default-jre-headless \
      tcpdump \
      net-tools \
      iputils-ping \
      dnsutils \
      openssh-client \
      telnet \
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

ENV JAVA_HOME=/opt/java \
    HADOOP_HOME=/opt/hadoop \
    HADOOP_CONF_DIR=/etc/hadoop/conf \
    ARROW_LIBHDFS_DIR=/opt/hadoop/lib/native \
    LD_LIBRARY_PATH=/opt/java/lib/server:/opt/hadoop/lib/native \
    CLASSPATH=/etc/hadoop/conf:/opt/hadoop/share/hadoop/common/*:/opt/hadoop/share/hadoop/common/lib/*:/opt/hadoop/share/hadoop/hdfs/*:/opt/hadoop/share/hadoop/hdfs/lib/*
ENV PATH=/opt/hadoop/bin:${PATH}

# Pin the client distribution and verify Apache's release checksums.
RUN set -eu; \
    case "$(dpkg --print-architecture)" in \
      amd64) archive=hadoop-3.5.0.tar.gz; \
        checksum=04ab94496cc00c8b7a28d03f6308eff8d2a4e7f37a9da5e8e086e4d6fc990e7a94d661908f6a6136039536efb362614b8aecdef185b5fb8ed588f0b152c7aa16 ;; \
      arm64) archive=hadoop-3.5.0-aarch64.tar.gz; \
        checksum=feaa20fea4709050ee993aae23b05720383a0d65aeda97c68d042e52564e8e77a83196a5a6973abdc690a1e600a73308ade56ccf9baeec231d1cf0810703430f ;; \
      *) echo "Unsupported Hadoop client architecture" >&2; exit 1 ;; \
    esac; \
    curl --fail --silent --show-error --location --retry 3 \
      "https://downloads.apache.org/hadoop/common/hadoop-3.5.0/$archive" \
      --output /tmp/hadoop.tar.gz; \
    echo "$checksum  /tmp/hadoop.tar.gz" | sha512sum --check -; \
    mkdir -p "$HADOOP_HOME" "$HADOOP_CONF_DIR"; \
    tar -xzf /tmp/hadoop.tar.gz -C "$HADOOP_HOME" --strip-components=1 \
      hadoop-3.5.0/lib/native hadoop-3.5.0/share/hadoop/common \
      hadoop-3.5.0/share/hadoop/hdfs hadoop-3.5.0/LICENSE.txt \
      hadoop-3.5.0/NOTICE.txt hadoop-3.5.0/bin/hdfs \
      hadoop-3.5.0/bin/hadoop hadoop-3.5.0/libexec; \
    tar -xzf /tmp/hadoop.tar.gz -C "$HADOOP_CONF_DIR" --strip-components=3 \
      hadoop-3.5.0/etc/hadoop; \
    rm /tmp/hadoop.tar.gz; \
    ln -s "$(dirname "$(dirname "$(readlink -f /usr/bin/java)")")" "$JAVA_HOME"

RUN printf '%s\n' \
      'log4j.rootLogger=WARN,console' \
      'log4j.appender.console=org.apache.log4j.ConsoleAppender' \
      'log4j.appender.console.Target=System.err' \
      'log4j.appender.console.layout=org.apache.log4j.PatternLayout' \
      'log4j.appender.console.layout.ConversionPattern=%p %c: %m%n' \
      > "$HADOOP_CONF_DIR/log4j.properties"

# Hadoop's CLI validates all component homes, even for filesystem-only commands.
ENV HADOOP_YARN_HOME=/opt/hadoop HADOOP_MAPRED_HOME=/opt/hadoop
RUN hdfs version && hadoop version

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/deciflow-venv \
    DECIFLOW_DATA_DIR=/var/lib/deciflow-data \
    PYTHONUNBUFFERED=1
RUN mkdir -p /var/lib/deciflow-data/actions /var/lib/deciflow-data/criteria
EXPOSE 4000
CMD ["sh", "-c", "uv sync --frozen --no-dev --no-install-project --no-cache && exec /opt/deciflow-venv/bin/python -c \"from deciflow import server; server.main(host='0.0.0.0')\""]
