from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.services.ai_usage import get_ai_service

router = APIRouter()


@router.get("/dashboard")
async def ai_usage_dashboard(
    date: str = Query(default=""),
    user: str = Query(default=""),
    model: str = Query(default=""),
    feature: str = Query(default=""),
) -> dict:
    return get_ai_service().store.dashboard(
        {
            "date": date,
            "user": user,
            "model": model,
            "feature": feature,
        }
    )


@router.get("/export.csv")
async def export_ai_usage_csv(
    date: str = Query(default=""),
    user: str = Query(default=""),
    model: str = Query(default=""),
    feature: str = Query(default=""),
) -> PlainTextResponse:
    csv_content = get_ai_service().store.csv_export(
        {
            "date": date,
            "user": user,
            "model": model,
            "feature": feature,
        }
    )
    return PlainTextResponse(
        csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="jobyro-ai-usage.csv"'},
    )
