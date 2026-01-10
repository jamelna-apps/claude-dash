FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/mlx-tools

# Copy requirements and install Python packages
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy MLX tools source
COPY . .

# Make mlx script executable
RUN chmod +x mlx

# Set environment
ENV PYTHONUNBUFFERED=1
ENV MEMORY_ROOT=/app/claude-memory
ENV PROJECTS_ROOT=/data/projects

# Default command (can be overridden)
ENTRYPOINT ["python"]
CMD ["--help"]
