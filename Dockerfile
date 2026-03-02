# Use official Python 3.13 slim image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    # Prevent uv from installing Python (we already have it in the image)
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1

# Install uv installer safely
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory
WORKDIR /app

# Enable dependency installation caching
# First, copy ONLY the dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies securely and efficiently. 
# --frozen ensures uv.lock is exactly matched without updating it.
RUN uv sync --frozen --no-dev

# Now copy the rest of your project files
COPY . .

# Put the virtual environment in the path
ENV PATH="/app/.venv/bin:$PATH"

# Expose port (metadata, but helpful)
EXPOSE 8000

# The Startup Command: 
# 1. Rebuilds the SQLite database so fresh mock data is always there
# 2. Starts Chainlit, binding it to 0.0.0.0 so the internet can reach it
CMD python init_db.py && chainlit run app.py -h --host 0.0.0.0 --port ${PORT:-8000}