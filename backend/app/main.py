from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import ai_usage, auth, health, profile, profiles, resume_intelligence, resumes
from app.core.config import settings

app = FastAPI(title="Jobyro API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
app.include_router(profiles.router, prefix="/api/profiles", tags=["profiles"])
app.include_router(resumes.router, prefix="/api/resumes", tags=["resumes"])
app.include_router(resume_intelligence.router, prefix="/api/resume-intelligence", tags=["resume-intelligence"])
app.include_router(ai_usage.router, prefix="/api/ai-usage", tags=["ai-usage"])
