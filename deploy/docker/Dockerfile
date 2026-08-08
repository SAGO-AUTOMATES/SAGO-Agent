FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy project
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev

COPY . .
RUN uv pip install -e .

# Create data dir
RUN mkdir -p /root/.sago

EXPOSE 7654

# Default: run daemon in foreground
CMD ["uv", "run", "sago", "serve", "--foreground"]
