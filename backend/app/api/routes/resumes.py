from io import BytesIO

from fastapi import APIRouter, HTTPException, Query
from fastapi import Depends, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.resume import (
    ExportResumeRequest,
    GenerateResumeRequest,
    GenerateResumeResponse,
    JobAnalysisRequest,
    JobAnalysisResponse,
    PhaseOneJobIntelligenceResponse,
    ProfileMatchRequest,
    ProfileMatchResponse,
    RequirementIntelligenceRequest,
    RequirementIntelligenceResponse,
    ResumeStrategyRequest,
    ResumeStrategyResponse,
    StructuredResumeRecord,
    UpdateStructuredResumeRequest,
)
from app.services.llm import (
    analyze_job_for_resume,
    analyze_job_intelligence_only,
    analyze_requirement_intelligence,
    analyze_resume_strategy,
    generate_resume,
)
from app.services.profile_matching import match_job_to_profile
from app.services import auth_store, profile_service
from app.services.profile_service import ProfileNotFoundError, ProfileOwnershipError, user_id_from_email
from app.services.resume_generation_pipeline import (
    assemble_structured_resume,
    build_generation_context,
    build_generation_response,
    select_relevant_profile_evidence,
)
from app.services.resume_store import (
    ResumeNotFoundError,
    ResumeOwnershipError,
    create_generated_resume,
    delete_resume,
    get_resume,
    list_resume_versions,
    list_resumes,
    save_resume_version,
    update_resume,
)
from app.services.resume_validator import validate_structured_resume
from app.services.ats_validator import validate_resume_content
from app.services.export import ExportFormat, export_resume_record
from app.services.export.export_service import ResumeExportValidationError
from app.services.export.template_registry import TemplateNotFoundError
from app.services.resume_export import build_docx, build_pdf, resume_filename

router = APIRouter()


async def db_session():
    from app.core.database import get_session

    async for session in get_session():
        yield session


def optional_current_user_id(authorization: str = Header(default="")):
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        user = auth_store.user_from_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid session.") from exc
    return user_id_from_email(user["email"])


@router.post("/analyze", response_model=JobAnalysisResponse)
async def analyze_resume_job(payload: JobAnalysisRequest) -> JobAnalysisResponse:
    try:
        return await analyze_job_for_resume(payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Job analysis failed: {exc}") from exc


@router.post("/job-intelligence", response_model=PhaseOneJobIntelligenceResponse)
async def analyze_resume_job_intelligence(payload: JobAnalysisRequest) -> PhaseOneJobIntelligenceResponse:
    try:
        return await analyze_job_intelligence_only(payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Job intelligence failed: {exc}") from exc


@router.post("/requirement-intelligence", response_model=RequirementIntelligenceResponse)
async def analyze_resume_requirements(payload: RequirementIntelligenceRequest) -> RequirementIntelligenceResponse:
    try:
        phase_one = payload.job_intelligence or await analyze_job_intelligence_only(payload)
        return await analyze_requirement_intelligence(payload, phase_one)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Requirement intelligence failed: {exc}") from exc


@router.post("/resume-strategy", response_model=ResumeStrategyResponse)
async def analyze_resume_strategy_phase(payload: ResumeStrategyRequest) -> ResumeStrategyResponse:
    try:
        return await analyze_resume_strategy(payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Resume strategy failed: {exc}") from exc


@router.post("/match-profile", response_model=ProfileMatchResponse)
async def match_resume_profile(
    payload: ProfileMatchRequest,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(optional_current_user_id),
) -> ProfileMatchResponse:
    try:
        if payload.profile_id:
            if user_id is None:
                raise HTTPException(status_code=401, detail="Missing bearer token.")
            record = await profile_service.get_profile(session, user_id, payload.profile_id)
            return match_job_to_profile(
                payload.job_analysis,
                record.profile_data,
                record.profile_id,
                record.updated_at,
                record.profile_version,
                record.content_hash,
            )
        # Temporary legacy path: candidate_profile-only requests are supported until the frontend
        # migration is complete. Persisted profileId always wins when both are supplied.
        return match_job_to_profile(
            payload.job_analysis,
            payload.candidate_profile,
            "legacy-client-profile",
            payload.profile_updated_at,
        )
    except ProfileOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Profile matching failed: {exc}") from exc


@router.post("/generate", response_model=GenerateResumeResponse)
async def create_resume(
    payload: GenerateResumeRequest,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(optional_current_user_id),
) -> GenerateResumeResponse:
    try:
        if payload.profile_id:
            if user_id is None:
                raise HTTPException(status_code=401, detail="Missing bearer token.")
            profile_record = await profile_service.get_profile(session, user_id, payload.profile_id)
            job_analysis = payload.job_analysis or await analyze_job_for_resume(payload)
            context = build_generation_context(profile_record, payload, job_analysis)
            selected = select_relevant_profile_evidence(context)
            structured = assemble_structured_resume(profile_record.profile_data, payload, context, selected)
            validation = validate_structured_resume(structured, context.evidence_index, context.profile_match)
            if validation.errors:
                structured = structured.model_copy(update={"status": "draft"})
            persisted = await create_generated_resume(
                session,
                user_id,
                structured,
                job_analysis.model_dump(mode="json", by_alias=True),
                context.profile_match.model_dump(mode="json", by_alias=True),
            )
            response = build_generation_response(profile_record.profile_data, payload, context, persisted.resume_json, validation)
            return response.model_copy(update={"persisted_resume_id": persisted.resume_id})
        return await generate_resume(payload)
    except ProfileOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Resume generation failed: {exc}") from exc


@router.get("", response_model=list[StructuredResumeRecord])
async def list_structured_resumes(
    session: AsyncSession = Depends(db_session),
    user_id=Depends(optional_current_user_id),
) -> list[StructuredResumeRecord]:
    if user_id is None:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    return await list_resumes(session, user_id)


@router.get("/{resume_id}", response_model=StructuredResumeRecord)
async def get_structured_resume(
    resume_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(optional_current_user_id),
) -> StructuredResumeRecord:
    if user_id is None:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    try:
        return await get_resume(session, user_id, resume_id)
    except ResumeOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{resume_id}", response_model=StructuredResumeRecord)
async def update_structured_resume(
    resume_id: str,
    payload: UpdateStructuredResumeRequest,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(optional_current_user_id),
) -> StructuredResumeRecord:
    if user_id is None:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    try:
        return await update_resume(session, user_id, resume_id, payload.resume_json, payload.status)
    except ResumeOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{resume_id}/versions", response_model=StructuredResumeRecord)
async def save_structured_resume_version(
    resume_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(optional_current_user_id),
) -> StructuredResumeRecord:
    if user_id is None:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    try:
        return await save_resume_version(session, user_id, resume_id)
    except ResumeOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{resume_id}/versions", response_model=list[StructuredResumeRecord])
async def list_structured_resume_versions(
    resume_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(optional_current_user_id),
) -> list[StructuredResumeRecord]:
    if user_id is None:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    try:
        return await list_resume_versions(session, user_id, resume_id)
    except ResumeOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{resume_id}", status_code=204)
async def delete_structured_resume(
    resume_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(optional_current_user_id),
) -> None:
    if user_id is None:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    try:
        await delete_resume(session, user_id, resume_id)
    except ResumeOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{resume_id}/export/pdf")
async def export_structured_resume_pdf(
    resume_id: str,
    template_id: str = Query(default="", alias="template_id"),
    paper_size: str = Query(default="letter"),
    filename: str = Query(default=""),
    session: AsyncSession = Depends(db_session),
    user_id=Depends(optional_current_user_id),
) -> StreamingResponse:
    return await export_persisted_resume(
        resume_id,
        ExportFormat.pdf,
        template_id=template_id,
        paper_size=paper_size,
        filename=filename,
        session=session,
        user_id=user_id,
    )


@router.get("/{resume_id}/export/docx")
async def export_structured_resume_docx(
    resume_id: str,
    template_id: str = Query(default="", alias="template_id"),
    paper_size: str = Query(default="letter"),
    filename: str = Query(default=""),
    session: AsyncSession = Depends(db_session),
    user_id=Depends(optional_current_user_id),
) -> StreamingResponse:
    return await export_persisted_resume(
        resume_id,
        ExportFormat.docx,
        template_id=template_id,
        paper_size=paper_size,
        filename=filename,
        session=session,
        user_id=user_id,
    )


async def export_persisted_resume(
    resume_id: str,
    export_format: ExportFormat,
    *,
    template_id: str,
    paper_size: str,
    filename: str,
    session: AsyncSession,
    user_id,
) -> StreamingResponse:
    if user_id is None:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    try:
        record = await get_resume(session, user_id, resume_id)
        result = export_resume_record(
            record,
            export_format=export_format,
            template_id=template_id or None,
            paper_size=paper_size,
            requested_filename=filename,
        )
        return StreamingResponse(
            BytesIO(result.content),
            media_type=result.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{result.filename}"',
                "Content-Length": str(len(result.content)),
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Resume-Version": str(result.resume_version),
                "X-Template-Id": result.template_id,
                "X-Export-Renderer-Version": result.renderer_version,
            },
        )
    except ResumeOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TemplateNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ResumeExportValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Resume export failed: {exc}") from exc


@router.post("/export/docx")
async def export_docx(payload: ExportResumeRequest) -> StreamingResponse:
    try:
        validate_resume_content(payload.resume)
        content = build_docx(payload.resume)
        filename = resume_filename(payload.resume, "docx")
        return StreamingResponse(
            BytesIO(content),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Word export failed: {exc}") from exc


@router.post("/export/pdf")
async def export_pdf(payload: ExportResumeRequest) -> StreamingResponse:
    try:
        validate_resume_content(payload.resume)
        content = build_pdf(payload.resume)
        filename = resume_filename(payload.resume, "pdf")
        return StreamingResponse(
            BytesIO(content),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PDF export failed: {exc}") from exc
