import pytest
from pydantic import ValidationError

from app.schemas.resume import JobAnalysisResponse, JobKeywordAnalysisItem


def test_valid_explicit_keyword() -> None:
    item = JobKeywordAnalysisItem(
        id="languages:c-sharp",
        value="C#",
        normalizedValue="c#",
        category="Languages",
        sourceType="explicit",
        confidence="high",
        priority="high",
        priorityScore=95,
        directFromJD=True,
        evidenceText="Experience with C#/.NET",
        occurrenceCount=1,
    )

    assert item.source_type == "explicit"
    assert item.direct_from_jd is True
    assert item.term == "C#"


def test_valid_inferred_keyword() -> None:
    item = JobKeywordAnalysisItem(
        id="leadership:developer-mentoring",
        value="Developer Mentoring",
        normalizedValue="developer mentoring",
        category="Leadership",
        sourceType="inferred",
        confidence="medium",
        priority="medium",
        priorityScore=60,
        directFromJD=False,
    )

    assert item.source_type == "inferred"
    assert item.direct_from_jd is False


def test_valid_suggested_keyword() -> None:
    item = JobKeywordAnalysisItem(
        id="cloud:azure",
        value="Azure",
        normalizedValue="azure",
        category="Cloud",
        sourceType="suggested",
        confidence="low",
        priority="low",
        priorityScore=25,
        directFromJD=False,
        reason="Cloud platform was mentioned, but Azure was not named.",
    )

    assert item.source_type == "suggested"


def test_priority_score_below_zero_fails() -> None:
    with pytest.raises(ValidationError):
        JobKeywordAnalysisItem(
            id="bad:score",
            value="Bad",
            normalizedValue="bad",
            category="General",
            sourceType="inferred",
            confidence="medium",
            priority="medium",
            priorityScore=-1,
            directFromJD=False,
        )


def test_priority_score_above_one_hundred_fails() -> None:
    with pytest.raises(ValidationError):
        JobKeywordAnalysisItem(
            id="bad:score",
            value="Bad",
            normalizedValue="bad",
            category="General",
            sourceType="inferred",
            confidence="medium",
            priority="medium",
            priorityScore=101,
            directFromJD=False,
        )


def test_occurrence_count_below_one_fails() -> None:
    with pytest.raises(ValidationError):
        JobKeywordAnalysisItem(
            id="bad:count",
            value="Bad",
            normalizedValue="bad",
            category="General",
            sourceType="inferred",
            confidence="medium",
            priority="medium",
            priorityScore=50,
            directFromJD=False,
            occurrenceCount=0,
        )


def test_suggested_direct_from_jd_true_fails() -> None:
    with pytest.raises(ValidationError):
        JobKeywordAnalysisItem(
            id="cloud:azure",
            value="Azure",
            normalizedValue="azure",
            category="Cloud",
            sourceType="suggested",
            confidence="low",
            priority="low",
            priorityScore=25,
            directFromJD=True,
        )


def test_existing_api_response_can_still_be_parsed() -> None:
    response = JobAnalysisResponse(
        roleInformation={"title": "Software Engineer", "seniority": "Senior"},
        technicalSkills={
            "languages": [
                {
                    "term": "C#",
                    "category": "Languages",
                    "priority": "critical",
                    "priorityScore": 9,
                    "recruiterWeight": 8,
                    "confidence": 0.95,
                    "explicit": True,
                }
            ]
        },
        explicitAtsKeywords=[
            {
                "term": ".NET",
                "category": "Frameworks",
                "priority": "important",
                "priorityScore": 8,
                "recruiterWeight": 8,
                "confidence": 0.85,
                "explicit": True,
            }
        ],
    )

    language = response.technical_skills["languages"][0]
    keyword = response.explicit_ats_keywords[0]

    assert language.value == "C#"
    assert language.priority_score == 90
    assert language.priority == "high"
    assert keyword.value == ".NET"
    assert keyword.priority_score == 80
