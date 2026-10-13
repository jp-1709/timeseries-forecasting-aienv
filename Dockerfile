# Dockerfile for FastAPI Price Prediction Service
FROM python:3.11-slim
 
WORKDIR /app
 
# Install build dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*
 
# Disable pip hash enforcement inside the image
ENV PIP_REQUIRE_HASHES=0

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
 
# Copy application code
COPY ./app ./app
COPY ./dashboard ./dashboard
COPY daily_update.py .
 
# Expose port (Render will override with PORT env var)
EXPOSE 8000
 
# Start the FastAPI app
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}

