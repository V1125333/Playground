from __future__ import annotations

import re


def sanitize_filename_part(value: str, *, fallback: str = "Resume", max_length: int = 80) -> str:
    cleaned = re.sub(r"[^\w\s-]", " ", value or "", flags=re.UNICODE)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = re.sub(r"-+", "-", cleaned)
    cleaned = cleaned.strip("._-")
    if not cleaned:
        cleaned = fallback
    return cleaned[:max_length].strip("._-") or fallback


def build_export_filename(
    *,
    full_name: str,
    target_role: str,
    company: str,
    version_number: int,
    extension: str,
    requested_filename: str = "",
) -> str:
    extension = extension.lower().lstrip(".")
    if requested_filename:
        requested_value = requested_filename.replace("\\", "/").split("/")[-1]
        requested_stem = requested_value.rsplit(".", 1)[0] if "." in requested_value else requested_value
        requested = sanitize_filename_part(requested_stem, fallback="Resume", max_length=140)
        return f"{requested}.{extension}"

    parts = [
        sanitize_filename_part(full_name, fallback="Resume", max_length=50),
        sanitize_filename_part(target_role, fallback="", max_length=55),
        sanitize_filename_part(company, fallback="", max_length=45),
        f"v{max(version_number, 1)}",
    ]
    stem = "_".join(part for part in parts if part)
    stem = re.sub(r"_+", "_", stem)[:150].strip("._-") or "Resume"
    return f"{stem}.{extension}"
