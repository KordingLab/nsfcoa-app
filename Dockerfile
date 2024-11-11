FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app

# Copy in the pyproject.toml and uv.lock files
COPY pyproject.toml uv.lock /app/

# Install the dependencies
RUN uv sync --no-dev

# Copy in the rest of the files
ADD . /app

# Run the application
CMD ["uv", "run", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
