# Stage 1: Build & install dependencies
FROM python:3.12-slim AS builder
WORKDIR /install
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Production runtime environment
FROM python:3.12-slim AS runtime
WORKDIR /app

# Copy installed dependencies from builder stage
COPY --from=builder /install /usr/local

# Copy application source code
COPY . .

# Normalize Windows line endings to Unix and make entrypoint script executable
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

# Run as a non-root user for security hardening
RUN useradd -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Exec entrypoint
ENTRYPOINT ["./entrypoint.sh"]
