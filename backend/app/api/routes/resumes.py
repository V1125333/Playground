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
from app.services.ai_usage import get_ai_service
from app.services.profile_matching import build_profile_evidence_index, calculate_non_overlapping_experience_months, match_job_to_profile
from app.services.experience_planner import build_experience_intelligence
from app.services.experience_prompt_builder import build_experience_prompts
from app.services.experience_generation_service import generate_experience_intelligence
from app.services import auth_store, profile_service
from app.services.profile_service import ProfileNotFoundError, ProfileOwnershipError, user_id_from_email
from app.services.resume_generation_pipeline import (
    assemble_structured_resume,
    build_generation_context,
    build_generation_context_from_profile_match,
    build_generation_response,
    select_relevant_profile_evidence,
)
from app.services.resume_intelligence_store import (
    ResumeIntelligencePackageNotFoundError,
    ResumeIntelligencePackageOwnershipError,
    ResumeIntelligencePackageStaleError,
    create_resume_intelligence_package,
    package_record_to_job_analysis,
    package_record_to_experience_intelligence,
    package_record_to_profile_match,
    validate_resume_intelligence_package,
)
from app.services.summary_intelligence import (
    SUMMARY_INTELLIGENCE_STALE_MESSAGE,
    build_summary_intelligence,
    summary_generation_from_intelligence,
    validate_summary_intelligence_for_package,
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
from app.services.summary_generation_service import generate_summary
from app.services.summary_planner import build_summary_planner, summary_job_id
from app.services.ats_validator import validate_resume_content
from app.services.export import ExportFormat, export_resume_record
from app.services.export.export_service import ResumeExportValidationError
from app.services.export.template_registry import TemplateNotFoundError
from app.services.resume_export import build_docx, build_pdf, resume_filename

router = APIRouter()


def normalized_text(value: str | None) -> str:
    return " ".join((value or "").strip().split()).casefold()


def normalized_unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = normalized_text(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def profile_location_tuple(location) -> tuple[str, str, str]:
    if location is None:
        return ("", "", "")
    return (
        normalized_text(getattr(location, "city", "")),
        normalized_text(getattr(location, "state", "") or ""),
        normalized_text(getattr(location, "country", "")),
    )


def profile_date_tuple(value) -> tuple[int, int]:
    if value is None:
        return (0, 0)
    return (int(getattr(value, "year", 0) or 0), int(getattr(value, "month", 0) or 0))


def validate_profile_snapshot(payload: GenerateResumeRequest, profile_record) -> None:
    if not payload.has_canonical_profile_snapshot:
        # Temporary legacy compatibility. Future removal: persisted-profile generation should
        # require the canonical profile snapshot from the frontend request builder.
        return
    missing = []
    if payload.profile_version is None:
        missing.append("profileVersion")
    if payload.candidate is None:
        missing.append("candidate")
    if payload.skills is None:
        missing.append("skills")
    if payload.work_experience is None:
        missing.append("workExperience")
    if payload.resume_preferences is None:
        missing.append("resumePreferences")
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing canonical profile snapshot fields: {', '.join(missing)}")

    if payload.profile_version != profile_record.profile_version:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Your profile has changed. Reload the latest profile before generating the resume.",
                "currentProfileVersion": profile_record.profile_version,
            },
        )

    profile = profile_record.profile_data
    assert payload.candidate is not None
    snapshot_name = f"{payload.candidate.first_name} {payload.candidate.last_name}"
    comparisons = [
        ("candidate name", snapshot_name, profile.name),
        ("current title", payload.candidate.current_title, profile.title),
        ("email", payload.candidate.email, profile.contact.email),
        ("phone", payload.candidate.phone, profile.contact.phone),
    ]
    mismatched = [label for label, left, right in comparisons if normalized_text(left) != normalized_text(right)]
    if profile.contact.location_data:
        if profile_location_tuple(payload.candidate.location) != profile_location_tuple(profile.contact.location_data):
            mismatched.append("location")
    elif normalized_text(payload.candidate.location.display_value) != normalized_text(profile.contact.location):
        mismatched.append("location")
    if mismatched:
        raise HTTPException(status_code=400, detail=f"Profile snapshot does not match persisted profile: {', '.join(mismatched)}")

    assert payload.skills is not None
    persisted_skill_groups = [
        (
            normalized_text(group.category),
            normalized_unique_texts(group.items),
        )
        for group in profile.skills
        if group.category.strip() and any(item.strip() for item in group.items)
    ]
    request_skill_groups = [
        (
            normalized_text(group.category_name),
            [normalized_text(item) for item in group.items if item.strip()],
        )
        for group in payload.skills
    ]
    if request_skill_groups != persisted_skill_groups:
        raise HTTPException(status_code=400, detail="Profile snapshot skills do not match persisted profile.")

    assert payload.work_experience is not None
    persisted_experience = {item.experience_id: item for item in profile.experience if item.experience_id}
    request_ids = [item.experience_id for item in payload.work_experience]
    if set(request_ids) != set(persisted_experience):
        raise HTTPException(status_code=400, detail="Profile snapshot workExperience does not match persisted profile.")
    for snapshot in payload.work_experience:
        record = persisted_experience[snapshot.experience_id]
        current = normalized_text(record.end_date) == "present"
        expected_end = "" if current else record.end_date
        checks = [
            ("companyName", snapshot.company_name, record.company),
            ("clientName", snapshot.client_name or "", record.client_name or ""),
            ("roleTitle", snapshot.role_title, record.role),
        ]
        location_mismatch = (
            profile_location_tuple(snapshot.location) != profile_location_tuple(record.location_data)
            if record.location_data
            else normalized_text(snapshot.location.display_value) != normalized_text(record.location)
        )
        start_mismatch = (
            profile_date_tuple(snapshot.start_date) != profile_date_tuple(record.start_date_data)
            if record.start_date_data
            else normalized_text(snapshot.start_date.display_value) != normalized_text(record.start_date)
        )
        end_mismatch = False
        if not current:
            end_mismatch = (
                profile_date_tuple(snapshot.end_date) != profile_date_tuple(record.end_date_data)
                if record.end_date_data
                else normalized_text(snapshot.end_date.display_value if snapshot.end_date else "") != normalized_text(expected_end)
            )
        if snapshot.is_current_role != current or location_mismatch or start_mismatch or end_mismatch or any(normalized_text(left) != normalized_text(right) for _, left, right in checks):
            raise HTTPException(
                status_code=400,
                detail=f"Profile snapshot workExperience item does not match persisted profile: {snapshot.experience_id}",
            )


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
            match_response = match_job_to_profile(
                payload.job_analysis,
                record.profile_data,
                record.profile_id,
                record.updated_at,
                record.profile_version,
                record.content_hash,
            )
            if payload.job_description:
                evidence_index = build_profile_evidence_index(record.profile_data, record.profile_id)
                summary_planner = build_summary_planner(
                    record.profile_data,
                    payload,
                    match_response.match_summary,
                    evidence_index,
                    round(calculate_non_overlapping_experience_months(record.profile_data) / 12, 1),
                )
                ai_service = get_ai_service()
                summary_build = await generate_summary(
                    profile=record.profile_data,
                    payload=payload,
                    job_analysis=payload.job_analysis,
                    profile_match=match_response.match_summary,
                    planner=summary_planner,
                    ai_service=ai_service,
                    job_id=summary_job_id(payload),
                    profile_version=record.profile_version,
                )
                summary_intelligence = build_summary_intelligence(
                    summary_build=summary_build,
                    model=ai_service.model_for("summary_generation"),
                    profile_record=record,
                    payload=payload,
                )
                experience_intelligence = build_experience_intelligence(
                    record.profile_data,
                    payload.job_description,
                    payload.job_analysis.normalized_requirements,
                    match_response.match_summary,
                    evidence_index,
                    payload.generation_settings,
                )
                experience_intelligence = build_experience_prompts(
                    experience_intelligence,
                    record.profile_data,
                    evidence_index,
                    payload.job_analysis.normalized_requirements,
                    payload,
                    payload.generation_settings,
                )
                experience_intelligence = await generate_experience_intelligence(experience_intelligence)
                package = await create_resume_intelligence_package(
                    session,
                    user_id,
                    profile_record=record,
                    payload=payload,
                    job_analysis=payload.job_analysis,
                    profile_match=match_response,
                    summary_intelligence=summary_intelligence,
                    experience_intelligence=experience_intelligence,
                )
                return match_response.model_copy(
                    update={
                        "package_id": package.package_id,
                        "job_description_hash": package.job_description_hash,
                        "summary_intelligence": summary_intelligence,
                        "experience_intelligence": experience_intelligence,
                        "validation_status": package.validation_status,
                        "validation_warnings": package.validation_warnings,
                    }
                )
            return match_response
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
            validate_profile_snapshot(payload, profile_record)
            summary_generation = None
            if payload.resume_intelligence_package_id:
                package_record = await validate_resume_intelligence_package(
                    session,
                    user_id,
                    payload.resume_intelligence_package_id,
                    profile_record,
                    payload,
                )
                job_analysis = package_record_to_job_analysis(package_record)
                try:
                    summary_intelligence = validate_summary_intelligence_for_package(package_record, profile_record, payload)
                except ValueError as exc:
                    raise ResumeIntelligencePackageStaleError(SUMMARY_INTELLIGENCE_STALE_MESSAGE) from exc
                summary_generation = summary_generation_from_intelligence(summary_intelligence)
                experience_intelligence = package_record_to_experience_intelligence(package_record)
                context = build_generation_context_from_profile_match(
                    profile_record,
                    payload,
                    job_analysis,
                    package_record_to_profile_match(package_record),
                )
            else:
                job_analysis = payload.job_analysis or await analyze_job_for_resume(payload)
                context = build_generation_context(profile_record, payload, job_analysis)
                summary_planner = build_summary_planner(
                    profile_record.profile_data,
                    payload,
                    context.profile_match,
                    context.evidence_index,
                    round(calculate_non_overlapping_experience_months(profile_record.profile_data) / 12, 1),
                )
                summary_build = await generate_summary(
                    profile=profile_record.profile_data,
                    payload=payload,
                    job_analysis=job_analysis,
                    profile_match=context.profile_match,
                    planner=summary_planner,
                    ai_service=get_ai_service(),
                    job_id=summary_job_id(payload),
                    profile_version=profile_record.profile_version,
                )
                summary_generation = summary_build.generation
                experience_intelligence = None
            selected = select_relevant_profile_evidence(context)
            structured = assemble_structured_resume(
                profile_record.profile_data,
                payload,
                context,
                selected,
                summary_generation,
                experience_intelligence,
            )
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
            return response.model_copy(update={"resume_id": persisted.resume_id, "persisted_resume_id": persisted.resume_id})
        return await generate_resume(payload)
    except HTTPException:
        raise
    except ProfileOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResumeIntelligencePackageOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ResumeIntelligencePackageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ResumeIntelligencePackageStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
