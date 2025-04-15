FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# 设置时区为 Asia/Shanghai（东八区）
RUN apt-get update && \
    apt-get install -y tzdata && \
    ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone

# 安装常用工具和开发环境
RUN apt-get update && apt-get install -y \
    curl \
    python3 \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN curl -LsSf https://astral.sh/uv/install.sh | bash
