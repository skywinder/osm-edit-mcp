# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./
COPY README.md ./

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Copy application code
COPY src/ ./src/
COPY web_server.py ./

# Create non-root user for security
RUN useradd -m -u 1000 osmuser && chown -R osmuser:osmuser /app
USER osmuser

# Expose port for web server
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Default command runs the web server
CMD ["python", "-m", "uvicorn", "web_server:app", "--host", "0.0.0.0", "--port", "8000"]