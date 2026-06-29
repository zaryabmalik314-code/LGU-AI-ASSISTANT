# LGU Degree Recommendation System

Production-ready backend recommendation pipeline for university admissions. Built using **FastAPI**, **PostgreSQL** (SQLAlchemy & Alembic), and **Redis** (caching and rate limiting).

## Architecture Pipeline

1. **Student Profile Input**
2. **Deterministic Rule Engine** (Only component deciding eligibility)
3. **Structured SQL Fetch** (Direct database retrieval, no vector DB/RAG lookup)
4. **Deterministic Ranking** (Top 3 sorting based on weight overlap)
5. **LLM Explanation** (Only explains the pre-computed ranking; fallback template on any failure)

---

## Local Setup

### 1. Manual Setup
```bash
# Set up virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment configuration (copy and adjust values)
cp .env.example .env

# Run database migrations
alembic upgrade head

# Launch development server
uvicorn app.main:app --reload
```

### 2. Docker & Containerized Setup
We provide container infrastructure out-of-the-box. Ensure Docker is installed and running.

#### Build & Start Services (App + Postgres + Redis)
```bash
docker compose up --build
```
This command compiles the secure multi-stage Docker image, runs the database and cache instances, executes Alembic database migrations automatically via `entrypoint.sh` (with fail-fast safety checks), and binds the server to port `8000`.

---

## Deployment & Production Configurations

### Railway Deployment Readiness
The project is configured for automated builds on Railway.
1. Connect your GitHub repository to Railway.
2. Railway will discover the `Dockerfile` in the root folder automatically.
3. Configure the following **Environment Variables** in Railway's dashboard:
   - `DATABASE_URL`: Set to your provisioned Postgres connection string.
   - `REDIS_URL`: Set to your provisioned Redis connection string.
   - `GROQ_API_KEY`: Your Groq/OpenAI compatible API key.
   - `LOG_LEVEL`: `INFO`
4. Railway binds the application port dynamically using the `$PORT` environment variable. Our entrypoint adapts automatically (`--port ${PORT:-8000}`).

---

## Observability & Health Endpoints

### 1. Health Check Endpoint
* **Path**: `GET /health`
* **Purpose**: Used for heartbeat checks and orchestration deployments (Kubernetes, AWS ECS, Railway, etc.).
* **Behavior**:
  * Returns `HTTP 200 OK` if the critical database dependency is connected.
  * If Redis is offline, it degrades gracefully (reporting `cache: unreachable` but still returning `HTTP 200` to prevent unnecessary app downtime).
  * Returns `HTTP 503 Service Unavailable` if database queries fail.

### 2. Request Tracking & Timing
All incoming API requests are assigned a unique transaction ID (`X-Request-ID`), either read from ingress headers or generated at runtime. This ID is automatically injected in response headers and prefixed to every application log line via `contextvars` to enable precise trace auditing. Request duration is logged in milliseconds.

---

## Testing

Run all unit, integration, and security test suites locally:
```bash
python -m pytest -v
```
All tests run with mocked adapters and do not require external cloud service credentials.
