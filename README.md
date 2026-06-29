# LGU Degree Recommendation System

Stack: FastAPI + Postgres (SQLAlchemy + Alembic)

## Setup
```
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://user:pass@localhost:5432/lgu_rec
alembic upgrade head
uvicorn app.main:app --reload
```

## Phases done
1. Schema (programs, admission_rules, program_content, recommendation_log)
2. Deterministic Rule Engine (app/rules/engine.py) — only component allowed to decide eligibility, fully unit tested
3. Structured fetch (app/rules/fetch.py) — direct SQL by program_id, no embeddings/vector search
4. (next) Deterministic ranking
5. (next) LLM explanation layer
...see full roadmap doc.

## Test
```
PYTHONPATH=. pytest tests/ -v
```

## Endpoint
`POST /recommend/eligible` — student profile in, eligible programs + full content out, rejected list for debug (never shown to LLM/user).
