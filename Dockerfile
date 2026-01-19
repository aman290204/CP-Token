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

COPY requirements_standalone.txt .
RUN pip install --no-cache-dir -r requirements_standalone.txt

COPY . .

CMD ["python3", "main.py"]
