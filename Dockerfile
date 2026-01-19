FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    ffmpeg \
    aria2 \
    wget \
    unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Optimize aria2 configuration for maximum speed
RUN mkdir -p /etc/aria2 \
    && echo "disable-ipv6=true\n" \
         "file-allocation=falloc\n" \
         "optimize-concurrent-downloads=true\n" \
         "max-concurrent-downloads=10\n" \
         "max-connection-per-server=16\n" \
         "split=16\n" \
         "min-split-size=1M\n" \
         "continue=true\n" \
         "check-integrity=true" > /etc/aria2/aria2.conf

# Start aria2c daemon for RPC and then run the bot
CMD aria2c --enable-rpc --rpc-listen-all --daemon=true && python3 main.py
