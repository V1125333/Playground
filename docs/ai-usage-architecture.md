# Jobyro AI Usage, Cost, and Monitoring Architecture

## Overview

Jobyro routes OpenAI calls through one backend service: `app.services.ai_usage.AIService`.
Resume pages and route handlers should not call OpenAI directly.

The service provides:

- Model routing by task.
- Request retry.
- Response caching for repeat analysis work.
- Token, latency, cost, status, and cache-hit logging.
- Dashboard and CSV export data.

## Model Configuration

Model names live in `.env`, not business logic:

- `AI_MODEL_JOB_INTELLIGENCE`
- `AI_MODEL_SEMANTIC_MAPPING`
- `AI_MODEL_RESUME_STRATEGY`
- `AI_MODEL_RESUME_GENERATION`
- `AI_MODEL_ATS_VALIDATION`
- `AI_MODEL_FORMATTING`

The default requested routing is:

- Job Intelligence: `gpt-5.5`
- Semantic Requirement Mapping: `gpt-5.5`
- Resume Strategy: `gpt-5.5`
- Resume Generation: `gpt-5.5`
- ATS Validation: `gpt-5.5-mini`
- Formatting / Cleanup: `gpt-5.5-mini`

If a model name is not available for the API account, change the `.env` value without editing the pipeline code.

## Pricing

Pricing is centralized in `AI_PRICING_JSON`.

Example:

```json
{
  "gpt-5.5": { "input": 0, "cached_input": 0, "output": 0 },
  "gpt-5.5-mini": { "input": 0, "cached_input": 0, "output": 0 }
}
```

Prices are interpreted as dollars per 1 million tokens.
The default values are zero until real pricing is entered.

## Caching

The service caches repeat analysis calls in `backend/data/ai_usage.sqlite3`.

Cached today:

- Job Intelligence
- ATS Keyword Extraction / Job Description Analysis
- Requirement Intelligence / Semantic Requirement Mapping

Cache keys include the feature, model, job description, target role, target company, level, and upstream phase output when relevant.
Local cache hits are logged as usage events with zero estimated cost.

## Usage Tracking

Every AI call creates an `ai_usage_events` record with:

- Timestamp
- User
- Feature
- Model
- Purpose
- Input tokens
- Output tokens
- Total tokens
- Estimated cost
- Latency
- Status
- Resume ID
- Job ID
- Cache hit
- Error text when applicable

The local store is SQLite so the development app can run without a Postgres migration.
The table shape is intentionally portable to a future SQLAlchemy/Postgres migration.

## Dashboard

The admin dashboard is available at:

`/ai-usage`

Backend endpoints:

- `GET /api/ai-usage/dashboard`
- `GET /api/ai-usage/export.csv`

Dashboard sections:

- Today's requests
- Today's cost
- Monthly cost
- Total tokens
- Average cost per resume
- Cache hit rate
- Average response time
- Usage by model
- Cost by day
- Request table with filters

## Resume Metrics

Every generated resume response includes `aiMetrics`:

- Generation time
- AI cost
- Tokens used
- Models used
- Cache used
- ATS score
- Validation score

The Generate page displays those metrics below the ATS card.

## Development Rules

- Do not call OpenAI directly from route handlers or UI code.
- Add new AI tasks through `AIService.chat_completion`.
- Put model names in `.env`, not inline code.
- Add cache keys only for deterministic, repeatable analysis work.
- Do not cache final resume generation unless the UX explicitly asks for identical resume reuse.
