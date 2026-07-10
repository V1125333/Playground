from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from openai import AsyncOpenAI

from app.core.config import ROOT_DIR, settings


MODEL_KEY_TO_SETTING = {
    "job_intelligence": "ai_model_job_intelligence",
    "semantic_mapping": "ai_model_semantic_mapping",
    "resume_strategy": "ai_model_resume_strategy",
    "resume_generation": "ai_model_resume_generation",
    "ats_validation": "ai_model_ats_validation",
    "formatting": "ai_model_formatting",
}

DEFAULT_PRICING = {
    "gpt-5.5": {"input": 0.0, "cached_input": 0.0, "output": 0.0},
    "gpt-5.5-mini": {"input": 0.0, "cached_input": 0.0, "output": 0.0},
}


@dataclass(frozen=True)
class AICompletionResult:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float
    latency_ms: int
    cache_hit: bool


class AIUsageStore:
    def __init__(self, db_path: str) -> None:
        path = Path(db_path)
        if not path.is_absolute():
            path = ROOT_DIR / path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user TEXT NOT NULL,
                    feature TEXT NOT NULL,
                    model TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    estimated_cost REAL NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    resume_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    cache_hit INTEGER NOT NULL,
                    error TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_response_cache (
                    cache_key TEXT PRIMARY KEY,
                    feature TEXT NOT NULL,
                    model TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def read_cache(self, cache_key: str) -> sqlite3.Row | None:
        with self._lock, self._connect() as connection:
            return connection.execute(
                "SELECT * FROM ai_response_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()

    def write_cache(
        self,
        *,
        cache_key: str,
        feature: str,
        model: str,
        request_hash: str,
        response_json: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        now = utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ai_response_cache (
                    cache_key, feature, model, request_hash, response_json,
                    input_tokens, output_tokens, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    response_json = excluded.response_json,
                    input_tokens = excluded.input_tokens,
                    output_tokens = excluded.output_tokens,
                    updated_at = excluded.updated_at
                """,
                (
                    cache_key,
                    feature,
                    model,
                    request_hash,
                    response_json,
                    input_tokens,
                    output_tokens,
                    now,
                    now,
                ),
            )
            connection.commit()

    def log_event(self, event: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ai_usage_events (
                    timestamp, user, feature, model, purpose, input_tokens,
                    output_tokens, total_tokens, estimated_cost, latency_ms,
                    status, resume_id, job_id, cache_hit, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["timestamp"],
                    event["user"],
                    event["feature"],
                    event["model"],
                    event["purpose"],
                    event["input_tokens"],
                    event["output_tokens"],
                    event["total_tokens"],
                    event["estimated_cost"],
                    event["latency_ms"],
                    event["status"],
                    event["resume_id"],
                    event["job_id"],
                    1 if event["cache_hit"] else 0,
                    event["error"],
                ),
            )
            connection.commit()

    def list_events(self, filters: dict[str, str]) -> list[dict[str, Any]]:
        query = "SELECT * FROM ai_usage_events WHERE 1=1"
        params: list[Any] = []
        if filters.get("date"):
            query += " AND substr(timestamp, 1, 10) = ?"
            params.append(filters["date"])
        if filters.get("user"):
            query += " AND lower(user) LIKE ?"
            params.append(f"%{filters['user'].lower()}%")
        if filters.get("model"):
            query += " AND model = ?"
            params.append(filters["model"])
        if filters.get("feature"):
            query += " AND feature = ?"
            params.append(filters["feature"])
        query += " ORDER BY timestamp DESC LIMIT 500"
        with self._lock, self._connect() as connection:
            return [row_to_event(row) for row in connection.execute(query, params).fetchall()]

    def dashboard(self, filters: dict[str, str]) -> dict[str, Any]:
        events = self.list_events(filters)
        now = datetime.now(UTC)
        today = now.date().isoformat()
        month = now.strftime("%Y-%m")
        all_events = self.list_events({})
        today_events = [item for item in all_events if item["timestamp"].startswith(today)]
        month_events = [item for item in all_events if item["timestamp"].startswith(month)]
        successful_non_cache = [item for item in all_events if item["status"] == "success" and not item["cacheHit"]]
        resume_ids = {item["resumeId"] for item in all_events if item["resumeId"]}
        total = len(all_events)
        cache_hits = sum(1 for item in all_events if item["cacheHit"])
        avg_cost_resume = sum(item["estimatedCost"] for item in all_events) / max(1, len(resume_ids))
        avg_latency = round(sum(item["latencyMs"] for item in all_events) / max(1, total))
        cost_by_day: dict[str, float] = {}
        usage_by_model: dict[str, int] = {}
        for item in all_events:
            day = item["timestamp"][:10]
            cost_by_day[day] = cost_by_day.get(day, 0.0) + item["estimatedCost"]
            usage_by_model[item["model"]] = usage_by_model.get(item["model"], 0) + item["totalTokens"]
        return {
            "cards": {
                "todayRequests": len(today_events),
                "todayCost": round(sum(item["estimatedCost"] for item in today_events), 6),
                "monthCost": round(sum(item["estimatedCost"] for item in month_events), 6),
                "totalTokens": sum(item["totalTokens"] for item in all_events),
                "averageCostPerResume": round(avg_cost_resume, 6),
                "cacheHitRate": round((cache_hits / total) * 100) if total else 0,
                "averageResponseTimeMs": avg_latency,
                "billableRequests": len(successful_non_cache),
            },
            "usageByModel": [
                {"model": model, "tokens": tokens} for model, tokens in sorted(usage_by_model.items())
            ],
            "costByDay": [
                {"date": day, "cost": round(cost, 6)} for day, cost in sorted(cost_by_day.items())
            ],
            "events": events,
        }

    def csv_export(self, filters: dict[str, str]) -> str:
        output = io.StringIO()
        fieldnames = [
            "timestamp",
            "user",
            "feature",
            "model",
            "tokens",
            "estimated_cost",
            "latency_ms",
            "status",
            "cache_hit",
            "resume_id",
            "job_id",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for item in self.list_events(filters):
            writer.writerow(
                {
                    "timestamp": item["timestamp"],
                    "user": item["user"],
                    "feature": item["feature"],
                    "model": item["model"],
                    "tokens": item["totalTokens"],
                    "estimated_cost": item["estimatedCost"],
                    "latency_ms": item["latencyMs"],
                    "status": item["status"],
                    "cache_hit": item["cacheHit"],
                    "resume_id": item["resumeId"],
                    "job_id": item["jobId"],
                }
            )
        return output.getvalue()


class AIService:
    def __init__(self) -> None:
        self.store = AIUsageStore(settings.ai_usage_db_path)
        self.pricing = load_pricing()
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    def model_for(self, model_key: str) -> str:
        setting_name = MODEL_KEY_TO_SETTING.get(model_key)
        if not setting_name:
            return settings.openai_model
        return getattr(settings, setting_name, settings.openai_model) or settings.openai_model

    async def chat_completion(
        self,
        *,
        feature: str,
        purpose: str,
        model_key: str,
        messages: list[dict[str, str]],
        response_format: dict[str, str] | None = None,
        temperature: float = 0.2,
        cache_parts: dict[str, Any] | None = None,
        user: str = "local-user",
        resume_id: str = "",
        job_id: str = "",
    ) -> AICompletionResult:
        model = self.model_for(model_key)
        cache_key = ""
        request_hash = stable_hash({"messages": messages, "responseFormat": response_format, "temperature": temperature})
        if cache_parts is not None:
            cache_key = stable_hash({"feature": feature, "model": model, "parts": cache_parts})
            cached = self.store.read_cache(cache_key)
            if cached:
                total_tokens = int(cached["input_tokens"] or 0) + int(cached["output_tokens"] or 0)
                self.store.log_event(
                    usage_event(
                        user=user,
                        feature=feature,
                        model=model,
                        purpose=purpose,
                        input_tokens=0,
                        output_tokens=0,
                        estimated_cost=0.0,
                        latency_ms=0,
                        status="cache_hit",
                        resume_id=resume_id,
                        job_id=job_id,
                        cache_hit=True,
                    )
                )
                return AICompletionResult(
                    content=str(cached["response_json"]),
                    model=model,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=total_tokens,
                    estimated_cost=0.0,
                    latency_ms=0,
                    cache_hit=True,
                )

        started = time.perf_counter()
        last_error = ""
        for attempt in range(2):
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if response_format:
                    kwargs["response_format"] = response_format
                completion = await self.client.chat.completions.create(**kwargs)
                latency_ms = round((time.perf_counter() - started) * 1000)
                content = completion.choices[0].message.content or ""
                usage = completion.usage
                input_tokens = int(getattr(usage, "prompt_tokens", 0) or estimate_tokens(messages))
                output_tokens = int(getattr(usage, "completion_tokens", 0) or estimate_tokens(content))
                cost = estimate_cost(model, input_tokens, output_tokens, self.pricing)
                self.store.log_event(
                    usage_event(
                        user=user,
                        feature=feature,
                        model=model,
                        purpose=purpose,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        estimated_cost=cost,
                        latency_ms=latency_ms,
                        status="success",
                        resume_id=resume_id,
                        job_id=job_id,
                        cache_hit=False,
                    )
                )
                if cache_key and content:
                    self.store.write_cache(
                        cache_key=cache_key,
                        feature=feature,
                        model=model,
                        request_hash=request_hash,
                        response_json=content,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    )
                return AICompletionResult(
                    content=content,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                    estimated_cost=cost,
                    latency_ms=latency_ms,
                    cache_hit=False,
                )
            except Exception as exc:
                last_error = str(exc)
                if attempt == 0:
                    continue
                latency_ms = round((time.perf_counter() - started) * 1000)
                self.store.log_event(
                    usage_event(
                        user=user,
                        feature=feature,
                        model=model,
                        purpose=purpose,
                        input_tokens=0,
                        output_tokens=0,
                        estimated_cost=0.0,
                        latency_ms=latency_ms,
                        status="error",
                        resume_id=resume_id,
                        job_id=job_id,
                        cache_hit=False,
                        error=last_error[:500],
                    )
                )
                raise
        raise RuntimeError(last_error or "AI call failed.")


def row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "user": row["user"],
        "feature": row["feature"],
        "model": row["model"],
        "purpose": row["purpose"],
        "inputTokens": row["input_tokens"],
        "outputTokens": row["output_tokens"],
        "totalTokens": row["total_tokens"],
        "estimatedCost": row["estimated_cost"],
        "latencyMs": row["latency_ms"],
        "status": row["status"],
        "resumeId": row["resume_id"],
        "jobId": row["job_id"],
        "cacheHit": bool(row["cache_hit"]),
        "error": row["error"],
    }


def usage_event(
    *,
    user: str,
    feature: str,
    model: str,
    purpose: str,
    input_tokens: int,
    output_tokens: int,
    estimated_cost: float,
    latency_ms: int,
    status: str,
    resume_id: str,
    job_id: str,
    cache_hit: bool,
    error: str = "",
) -> dict[str, Any]:
    return {
        "timestamp": utc_now(),
        "user": user,
        "feature": feature,
        "model": model,
        "purpose": purpose,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost": round(estimated_cost, 8),
        "latency_ms": latency_ms,
        "status": status,
        "resume_id": resume_id,
        "job_id": job_id,
        "cache_hit": cache_hit,
        "error": error,
    }


def load_pricing() -> dict[str, dict[str, float]]:
    if not settings.ai_pricing_json.strip():
        return DEFAULT_PRICING
    try:
        data = json.loads(settings.ai_pricing_json)
        return {
            model: {
                "input": float(values.get("input", 0.0)),
                "cached_input": float(values.get("cached_input", values.get("cachedInput", 0.0))),
                "output": float(values.get("output", 0.0)),
            }
            for model, values in data.items()
        }
    except Exception:
        return DEFAULT_PRICING


def estimate_cost(model: str, input_tokens: int, output_tokens: int, pricing: dict[str, dict[str, float]]) -> float:
    model_pricing = pricing.get(model, pricing.get("default", {"input": 0.0, "output": 0.0}))
    input_cost = (input_tokens / 1_000_000) * float(model_pricing.get("input", 0.0))
    output_cost = (output_tokens / 1_000_000) * float(model_pricing.get("output", 0.0))
    return round(input_cost + output_cost, 8)


def estimate_tokens(value: Any) -> int:
    text = json.dumps(value, ensure_ascii=True) if not isinstance(value, str) else value
    return max(1, round(len(text) / 4))


def stable_hash(value: Any) -> str:
    normalized = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def recent_job_id(job_description: str, target_role: str, company: str) -> str:
    return stable_hash({"jobDescription": job_description, "targetRole": target_role, "company": company})[:16]


_service: AIService | None = None


def get_ai_service() -> AIService:
    global _service
    if _service is None:
        _service = AIService()
    return _service
