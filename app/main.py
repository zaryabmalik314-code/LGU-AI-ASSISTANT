"""
LGU Degree Recommendation System — Main Application Entry Point (Phase 8).
"""
import os
import re
import logging
import hashlib
import json
import traceback
from datetime import datetime, date, timezone
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, Request, Depends, HTTPException, status
<<<<<<< HEAD
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
=======
from fastapi.responses import JSONResponse
>>>>>>> 8a9d3e6ac4e47537cef36e95790070b4289d40b4
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.models import AdmissionRule, RecommendationLog
from app.policy.router import router as policy_router
from app.policy.scheduler import start_scheduler
from app.rules.engine import StudentProfile, filter_eligible_programs, eligible_program_ids
from app.rules.fetch import fetch_program_details
from app.rules.ranking import ProgramScoreInput, rank_programs
from app.llm.orchestrator import generate_explanations
from app.cache.keys import build_bucket_key
import app.cache.redis_client as redis_client

import contextvars
import uuid
import time
from app.config import settings

# Request ID Context Variable
request_id_ctx_var = contextvars.ContextVar("request_id", default="-")

class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_ctx_var.get()
        return True

# Configure logging with RequestIdFilter
logger = logging.getLogger("app.main")

handler = logging.StreamHandler()
handler.addFilter(RequestIdFilter())
formatter = logging.Formatter("%(asctime)s [%(levelname)s] [RequestID: %(request_id)s] %(name)s: %(message)s")
handler.setFormatter(formatter)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
for h in list(root_logger.handlers):
    root_logger.removeHandler(h)
root_logger.addHandler(handler)

# ---------------------------------------------------------------------------
# Environment Validation & Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate environment variables on startup from settings
    db_url = settings.database_url
    if db_url and not (db_url.startswith("postgresql://") or db_url.startswith("postgresql+psycopg2://") or db_url.startswith("sqlite://")):
        logger.error("Startup Warning: DATABASE_URL does not start with expected schemes (postgresql:// or sqlite://)")

    redis_url = settings.redis_url
    if redis_url and not (redis_url.startswith("redis://") or redis_url.startswith("rediss://")):
        logger.error("Startup Warning: REDIS_URL does not start with expected schemes (redis:// or rediss://)")

    groq_key = settings.groq_api_key
    if not groq_key:
        logger.info("Startup Info: GROQ_API_KEY is not set. LLM explanation layer will fall back to templates.")
    else:
        logger.info("Startup Info: GROQ_API_KEY is configured.")

    # Start policy scheduler
    start_scheduler(app)
    yield

# Initialize FastAPI App
app = FastAPI(
    title="LGU Degree Recommendation System",
    description="Deterministic degree eligibility, ranking, and explanation pipeline.",
    version="1.0.0",
    lifespan=lifespan,
    contact={
        "name": "LGU IT Support & Admissions",
        "email": "support@lgu.edu.pk"
    }
)

# Register routers
app.include_router(policy_router)

# ---------------------------------------------------------------------------
<<<<<<< HEAD
# Frontend (video-driven mentor UI)
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/app", tags=["frontend"], summary="Serves the video-driven mentor frontend")
def serve_frontend():
    return FileResponse("app/static/index.html")

# ---------------------------------------------------------------------------
=======
>>>>>>> 8a9d3e6ac4e47537cef36e95790070b4289d40b4
# Pydantic Schemas for Input Validation
# ---------------------------------------------------------------------------

class StudentProfileRequest(BaseModel):
    matric_pct: float = Field(..., ge=0.0, le=100.0, description="Matriculation percentage")
    inter_pct: float = Field(..., ge=0.0, le=100.0, description="Intermediate percentage")
    inter_stream: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-zA-Z0-9\s\-\.\(\)]+$")
    subjects: List[str] = Field(default=[], max_length=20)
    interests: List[str] = Field(default=[], max_length=20)
    career_goals: List[str] = Field(default=[], max_length=20)

    @field_validator("subjects")
    @classmethod
    def validate_subjects(cls, v):
        pattern = re.compile(r"^[a-zA-Z0-9\s\-\.\(\)]+$")
        for item in v:
            if len(item) < 1 or len(item) > 50:
                raise ValueError("Subject string must be between 1 and 50 characters")
            if not pattern.match(item):
                raise ValueError("Subject contains invalid characters")
        return v

    @field_validator("interests", "career_goals")
    @classmethod
    def validate_free_text(cls, v):
        pattern = re.compile(r"^[a-zA-Z0-9\s\-\.\,\!\?\'\"\(\)]+$")
        for item in v:
            if len(item) < 1 or len(item) > 100:
                raise ValueError("Free text item must be between 1 and 100 characters")
            if not pattern.match(item):
                raise ValueError("Free text contains invalid characters")
        return v

# ---------------------------------------------------------------------------
# Security Middleware (Headers)
# ---------------------------------------------------------------------------

@app.middleware("http")
async def production_middleware(request: Request, call_next):
    # Determine request ID (read from client headers if present, e.g. from gateway, or generate)
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_ctx_var.set(request_id)
    
    start_time = time.perf_counter()
    client_ip = request.client.host if request.client else "unknown"
    
    logger.info(f"Incoming Request: {request.method} {request.url.path} from IP {client_ip}")
    
    try:
        response = await call_next(request)
        
        # Inject standard security and request tracking headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
<<<<<<< HEAD
        if request.url.path.startswith("/static") or request.url.path == "/app":
            # Frontend needs to load its own CSS/JS/video from same origin
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; media-src 'self'; img-src 'self' data:; "
                "style-src 'self' 'unsafe-inline'; script-src 'self'; "
                "connect-src 'self'; frame-ancestors 'none'"
            )
        else:
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
=======
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
>>>>>>> 8a9d3e6ac4e47537cef36e95790070b4289d40b4
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            f"Outgoing Response: {request.method} {request.url.path} - Status: {response.status_code} "
            f"- Duration: {duration_ms:.2f}ms"
        )
        return response
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.error(
            f"Request Failed: {request.method} {request.url.path} "
            f"- Duration: {duration_ms:.2f}ms - Error: {exc}"
        )
        raise
    finally:
        request_id_ctx_var.reset(token)

# ---------------------------------------------------------------------------
# Rate Limiting & Bot Protection
# ---------------------------------------------------------------------------

RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW_SECONDS = 60

def rate_limit(request: Request):
    if not redis_client.is_enabled():
        return  # Graceful degradation: bypass when Redis is not configured/unreachable
        
    client_ip = request.client.host if request.client else "unknown"
    key = f"ratelimit:{client_ip}"
    
    try:
        r = redis_client._client
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        results = pipe.execute()
        count = results[0]
        ttl = results[1]
        
        if count == 1 or ttl == -1:
            r.expire(key, RATE_LIMIT_WINDOW_SECONDS)
            
        if count > RATE_LIMIT_REQUESTS:
            logger.warning(f"Rate limit exceeded for IP {client_ip} (count: {count})")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Redis rate limiter encountered error, bypassing: {e}")

# ---------------------------------------------------------------------------
# Global Error Handlers
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please contact support."}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    from fastapi.encoders import jsonable_encoder
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(exc.errors())}
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_active_rule_rows(db: Session) -> list:
    from app.rules.engine import RuleRow
    today = date.today()
    db_rules = db.query(AdmissionRule).filter(
        AdmissionRule.effective_from <= today,
        (AdmissionRule.effective_to.is_(None)) | (AdmissionRule.effective_to >= today)
    ).all()
    
    return [
        RuleRow(
            id=r.id,
            program_id=r.program_id,
            allowed_streams=r.allowed_streams or [],
            min_matric_pct=r.min_matric_pct,
            min_inter_pct=r.min_inter_pct,
            required_subjects=r.required_subjects or [],
            effective_from=r.effective_from,
            effective_to=r.effective_to
        )
        for r in db_rules
    ]

def compute_profile_hash(profile: dict) -> str:
    norm = {
        "matric_pct": profile.get("matric_pct"),
        "inter_pct": profile.get("inter_pct"),
        "inter_stream": str(profile.get("inter_stream")).strip().lower(),
        "subjects": sorted([s.strip().lower() for s in profile.get("subjects", [])]),
        "interests": sorted([i.strip().lower() for i in profile.get("interests", [])]),
        "career_goals": sorted([c.strip().lower() for c in profile.get("career_goals", [])]),
    }
    serialized = json.dumps(norm, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

def save_recommendation_log(db: Session, log_entry: RecommendationLog):
    try:
        db.add(log_entry)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to write RecommendationLog to DB (expected in SQLite tests): {e}")

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["system"], summary="Root endpoint returning API status")
def read_root():
    """Returns basic status and system metadata."""
    return {"status": "healthy", "service": "LGU AI Recommendation System API"}


@app.get(
    "/health",
    tags=["system"],
    summary="Health check endpoint for container orchestration and deployments",
    response_description="A JSON representation of the health status of database and cache dependencies",
    responses={
        200: {
            "description": "Database is connected and healthy (Redis can be degraded/disabled)",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "database": "connected",
                        "cache": "connected",
                        "timestamp": "2026-06-30T00:00:00Z"
                    }
                }
            }
        },
        503: {
            "description": "Critical database dependency is offline",
            "content": {
                "application/json": {
                    "example": {
                        "status": "unhealthy",
                        "database": "disconnected: connection refused",
                        "cache": "unreachable",
                        "timestamp": "2026-06-30T00:00:00Z"
                    }
                }
            }
        }
    }
)
def health_check(db: Session = Depends(get_db)):
    """
    Checks connection status of critical dependencies:
    - **Database**: Must be reachable and respond to queries (critical).
    - **Cache**: Reached via Redis (non-critical, degrades gracefully).
    """
    from sqlalchemy import text
    health_status = {
        "status": "healthy",
        "database": "connected",
        "cache": "disabled",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Check database
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Health check Database failure: {e}")
        health_status["status"] = "unhealthy"
        health_status["database"] = f"disconnected: {str(e)}"
        
    # Check cache
    if redis_client.is_enabled():
        try:
            redis_client._client.ping()
            health_status["cache"] = "connected"
        except Exception as e:
            logger.warning(f"Health check Cache degraded: {e}")
            health_status["cache"] = f"unreachable: {str(e)}"
    else:
        health_status["cache"] = "disabled"
        
    if health_status["status"] == "unhealthy":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=health_status
        )
        
    return health_status

@app.post(
    "/recommend/eligible",
    dependencies=[Depends(rate_limit)],
    tags=["recommendation"],
    summary="Compute degree program recommendations for a student",
    response_description="Ranked eligible degree programs with structured explanations and a debug list of ineligible programs.",
    responses={
        200: {
            "description": "Successfully evaluated profile and generated recommendations"
        },
        422: {
            "description": "Validation error in student profile fields (percentages or strings containing illegal characters)"
        },
        429: {
            "description": "Rate limit exceeded (too many requests per minute)"
        },
        500: {
            "description": "Unhandled system or database error (traceback masked)"
        }
    }
)
def recommend_eligible_programs(request: StudentProfileRequest, db: Session = Depends(get_db)):
    logger.info("Processing student recommendation request")
    
    # 1. Map to engine student profile structure
    student_profile = StudentProfile(
        matric_pct=request.matric_pct,
        inter_pct=request.inter_pct,
        inter_stream=request.inter_stream,
        subjects=request.subjects,
        interests=request.interests,
        career_goals=request.career_goals
    )
    
    # 2. Query Rules Engine
    active_rules = get_active_rule_rows(db)
    eligibility_results = filter_eligible_programs(student_profile, active_rules)
    eligible_ids = eligible_program_ids(eligibility_results)
    
    matched_rule_versions = [
        r.rule_id for r in eligibility_results if r.eligible
    ]
    
    # Extract rejected programs for debug output
    rejected_list = [
        {
            "program_id": r.program_id,
            "rule_id": r.rule_id,
            "reasons_failed": r.reasons_failed
        }
        for r in eligibility_results if not r.eligible
    ]
    
    logger.info(f"Rules Evaluated: {len(eligible_ids)} eligible, {len(rejected_list)} rejected")
    
    # 3. Structured SQL Fetch
    program_details = fetch_program_details(db, eligible_ids)
    
    # 4. Deterministic Ranking (Top 3)
    score_inputs = [
        ProgramScoreInput(
            program_id=p["program_id"],
            interest_tags=p["interest_tags"] or [],
            career_keywords=p["career_keywords"] or [],
            stream_match=bool(
                p.get("preferred_stream") and 
                p["preferred_stream"].strip().lower() == request.inter_stream.strip().lower()
            )
        )
        for p in program_details
    ]
    
    ranked_results = rank_programs(
        programs=score_inputs,
        student_interests=request.interests,
        student_career_goals=request.career_goals,
        top_n=3
    )
    
    ranked_ids = [r.program_id for r in ranked_results]
    
    # Keep ranked details in order
    ranked_programs = [p for p in program_details if p["program_id"] in ranked_ids]
    ranked_programs.sort(key=lambda p: ranked_ids.index(p["program_id"]))
    
    # 5. LLM Explanation Layer with caching
    explanations = []
    source = "fallback_template"
    
    if ranked_ids:
        cache_key = build_bucket_key(
            ranked_program_ids=ranked_ids,
            interests=request.interests,
            career_goals=request.career_goals
        )
        cached = redis_client.get_cached(cache_key)
        if cached is not None:
            explanations = cached.get("explanations", [])
            source = "cache"
            logger.info("Explanation Cache: HIT")
        else:
            logger.info("Explanation Cache: MISS. Calling explanation layer")
            # Build student profile dictionary matching what orchestrator expects
            student_profile_dict = {
                "matric_pct": request.matric_pct,
                "inter_pct": request.inter_pct,
                "inter_stream": request.inter_stream,
                "subjects": request.subjects,
                "interests": request.interests,
                "career_goals": request.career_goals
            }
            exp_result = generate_explanations(student_profile_dict, ranked_programs)
            source = exp_result.source
            from dataclasses import asdict
            explanations = [asdict(e) for e in exp_result.explanations]
            
            # Store in cache
            redis_client.set_cached(cache_key, {"explanations": explanations})
            
    # 6. Database Logging
    norm_profile = {
        "matric_pct": request.matric_pct,
        "inter_pct": request.inter_pct,
        "inter_stream": request.inter_stream,
        "subjects": request.subjects,
        "interests": request.interests,
        "career_goals": request.career_goals
    }
    profile_hash = compute_profile_hash(norm_profile)
    
    log_entry = RecommendationLog(
        profile_hash=profile_hash,
        input_profile=norm_profile,
        eligible_program_ids=eligible_ids,
        ranked_program_ids=ranked_ids,
        rule_version_ids=matched_rule_versions,
        model_version="llama-3.3-70b-versatile",
        llm_output={"explanations": explanations, "source": source},
        created_at=datetime.now(timezone.utc).isoformat()
    )
    save_recommendation_log(db, log_entry)
    
    return {
        "eligible_programs": ranked_programs,
        "explanations": explanations,
        "source": source,
        "rejected_programs": rejected_list
<<<<<<< HEAD
    }
=======
    }
>>>>>>> 8a9d3e6ac4e47537cef36e95790070b4289d40b4
