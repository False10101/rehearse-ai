# ruff: noqa: E501

import json
import logging
import re
from typing import Literal

import requests
from pydantic import BaseModel, Field, ValidationError

from app.services.slide_analyzer import ANALYSIS_MODEL, OPENROUTER_API_URL, openrouter_headers

TRANSCRIPT_MODEL = ANALYSIS_MODEL
TRANSCRIPT_PROMPT_VERSION = "transcript-speaker-ready-v7"
logger = logging.getLogger(__name__)
Tone = Literal["auto", "persuasive", "informative", "conversational"]
Style = Literal["natural", "formal"]
AudienceLevel = Literal["beginner", "general", "specialist"]

AUDIENCE_RULES: dict[AudienceLevel, str] = {
    "beginner": (
        "Assume little prior subject knowledge. Use common words and short spoken sentences. "
        "Explain necessary technical terms and acronyms on first use, and build complicated "
        "ideas step by step. Use a brief clearly illustrative analogy only when it accurately "
        "explains supported content; never invent examples of actual results or events."
    ),
    "general": (
        "Assume an educated audience without specialist subject knowledge. Give concise context "
        "and explain necessary unfamiliar terms, while avoiding lengthy explanations of everyday ideas."
    ),
    "specialist": (
        "Assume relevant subject knowledge. Retain precise technical terminology and focus on "
        "supported mechanisms, distinctions, and details rather than basic definitions. "
        "Do not add technical claims absent from the source."
    ),
}

TONE_RULES: dict[Tone, str] = {
    "auto": (
        "Choose the primary delivery tone that best fits the slide's purpose. Keep that tone "
        "consistent throughout the script."
    ),
    "persuasive": (
        "Take a clear, supportable position. Connect evidence to audience benefit, use confident "
        "language, and finish with a recommendation, conclusion, or next step. Do not invent "
        "evidence, overstate certainty, or sound like an advertisement."
    ),
    "informative": (
        "Prioritize clear explanation. Organize facts and relationships logically, use neutral "
        "wording, and help the audience understand the point without pressuring them to agree."
    ),
    "conversational": (
        "Sound like a prepared person speaking directly to listeners, not reading an academic "
        "report. Use contractions, direct audience language where natural, shorter sentences, "
        "and relaxed spoken transitions. The content may still explain facts, but the delivery "
        "must remain recognizably conversational."
    ),
}

STYLE_RULES: dict[Style, str] = {
    "natural": (
        "Use an easy spoken rhythm, contractions, varied sentence lengths, and minimal formal "
        "signposting."
    ),
    "formal": (
        "Use polished vocabulary, complete sentences, and controlled transitions. Formal means "
        "professional, not academic or robotic, and it must not override the selected tone."
    ),
}


class GeneratedParagraphs(BaseModel):
    paragraphs: list[str] = Field(min_length=1, max_length=4)


class GeneratedComplexTerm(BaseModel):
    term: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    pronunciation: str = Field(min_length=1)
    why_complex: str = Field(min_length=1)


class GeneratedToneCheck(BaseModel):
    classification: Literal["Persuasive", "Informative", "Aggressive", "Neutral", "Conversational"]
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1)


class GeneratedVocabularyUpgrade(BaseModel):
    original: str = Field(min_length=1)
    suggested: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    issue: Literal["unclear", "wordy", "repetitive", "too-casual", "too-formal"]


class ScriptAnalysis(BaseModel):
    complex_terms: list[GeneratedComplexTerm] = Field(default_factory=list)
    tone_check: GeneratedToneCheck
    vocabulary_upgrades: list[GeneratedVocabularyUpgrade] = Field(default_factory=list)
    grounding_issues: list[str] = Field(default_factory=list)


class SelectionEnhancement(BaseModel):
    replacement_paragraphs: list[str] = Field(min_length=1)


def _parse_json_content(response: requests.Response) -> dict:
    try:
        response.raise_for_status()
    except requests.HTTPError:
        logger.error(
            "Transcript provider returned HTTP %s: %s",
            response.status_code,
            response.text[:12000],
        )
        raise
    choice = response.json()["choices"][0]
    content = choice.get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(
            "Transcript model returned no usable content "
            f"(finish_reason={choice.get('finish_reason')!r})."
        )
    content = content.strip()
    if content.startswith("```"):
        content = content.split("```", 2)[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.rsplit("```", 1)[0]
    try:
        result = json.loads(content.strip())
    except json.JSONDecodeError:
        logger.error("Transcript provider returned invalid JSON: %s", content[:12000])
        raise
    if not isinstance(result, dict):
        raise ValueError("Transcript model returned a non-object JSON response.")
    return result


def _request_json(prompt: str, max_tokens: int = 2200) -> dict:
    response = requests.post(
        OPENROUTER_API_URL,
        headers=openrouter_headers(),
        json={
            "model": TRANSCRIPT_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.25,
            "max_tokens": max_tokens,
        },
        timeout=120,
    )
    return _parse_json_content(response)


def _slide_context(slide: dict) -> str:
    return json.dumps(
        {
            "slide_number": slide.get("num"),
            "title": slide.get("title") or "",
            "text_content": slide.get("text", []),
            "tables": slide.get("tables", []),
            "visual_context": slide.get("img_context", []),
        },
        ensure_ascii=False,
    )


def _neighbor_summary(slide: dict | None) -> dict | None:
    if slide is None:
        return None
    visible_text: list[str] = []
    for item in slide.get("text", []):
        if isinstance(item, dict):
            text = str(item.get("t") or "").strip()
        else:
            text = str(item).strip()
        if text:
            visible_text.append(text)
    return {
        "slide_number": slide.get("num"),
        "title": slide.get("title") or "",
        "visible_text": visible_text[:12],
    }


def _deck_outline(slides: list[dict] | None) -> list[dict]:
    if not slides:
        return []
    outline = []
    for slide in slides:
        summary = _neighbor_summary(slide)
        if summary is None:
            continue
        outline.append(
            {
                "slide_number": summary["slide_number"],
                "title": summary["title"],
                "visible_text": [text[:240] for text in summary["visible_text"][:4]],
            }
        )
    return outline


def _normalized_phrase(value: str) -> str:
    return " ".join(value.casefold().split()).strip(" .,;:!?\"'()[]{}")


NON_COMPLEX_TERMS = {
    "ai",
    "ai matching",
    "ai-powered",
    "artificial intelligence",
    "competency",
    "competencies",
    "adaptability",
    "feedback loop",
    "job matching",
    "matching engine",
    "match score",
    "mismatch",
    "recruitment",
    "smart profile builder",
    "skill based job matching engine",
    "skill-based job matching engine",
    "structured feedback",
    "upskilling hub",
}

EVERYDAY_ACRONYMS = {"AI"}

ACRONYM_PRONUNCIATION = {
    "A": "ay",
    "B": "bee",
    "C": "see",
    "D": "dee",
    "E": "ee",
    "F": "ef",
    "G": "gee",
    "H": "aitch",
    "I": "eye",
    "J": "jay",
    "K": "kay",
    "L": "el",
    "M": "em",
    "N": "en",
    "O": "oh",
    "P": "pee",
    "Q": "cue",
    "R": "ar",
    "S": "ess",
    "T": "tee",
    "U": "you",
    "V": "vee",
    "W": "double you",
    "X": "ex",
    "Y": "why",
    "Z": "zee",
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}

STRONGER_CLAIM_WORDS = {
    "accurate",
    "accurately",
    "better",
    "effective",
    "effectively",
    "faster",
    "guarantee",
    "guaranteed",
    "improve",
    "improves",
    "increase",
    "increases",
    "proven",
    "reliable",
    "trusted",
}


def _adds_stronger_claim(original: str, suggested: str) -> bool:
    original_words = set(_normalized_phrase(original).replace("-", " ").split())
    suggested_words = set(_normalized_phrase(suggested).replace("-", " ").split())
    return bool((suggested_words - original_words) & STRONGER_CLAIM_WORDS)


def _required_acronyms(paragraphs: list[str]) -> list[str]:
    acronyms: list[str] = []
    for match in re.finditer(r"\b[A-Z][A-Z0-9]{1,9}\b", " ".join(paragraphs)):
        acronym = match.group(0)
        if acronym not in EVERYDAY_ACRONYMS and acronym not in acronyms:
            acronyms.append(acronym)
    return acronyms[:8]


def _acronym_pronunciation(acronym: str) -> str:
    return " ".join(ACRONYM_PRONUNCIATION[character] for character in acronym)


def _script_shape(duration_seconds: int) -> tuple[int, int, int, int]:
    target_words = round(duration_seconds * 145 / 60)
    if duration_seconds <= 45:
        return target_words, 1, 2, round(target_words * 0.78)
    if duration_seconds <= 75:
        return target_words, 2, 3, round(target_words * 0.78)
    return target_words, 3, 4, round(target_words * 0.78)


def _validate_spoken_script(result: dict, duration_seconds: int) -> list[str]:
    try:
        parsed = GeneratedParagraphs.model_validate(result)
    except ValidationError as error:
        raise ValueError(
            "Transcript response did not match the required paragraph schema."
        ) from error

    paragraphs = [paragraph.strip() for paragraph in parsed.paragraphs if paragraph.strip()]
    target_words, minimum_paragraphs, maximum_paragraphs, minimum_words = _script_shape(
        duration_seconds
    )
    if not minimum_paragraphs <= len(paragraphs) <= maximum_paragraphs:
        raise ValueError(
            f"Transcript needs {minimum_paragraphs}-{maximum_paragraphs} spoken paragraphs."
        )
    word_count = len(" ".join(paragraphs).split())
    maximum_words = round(target_words * 1.2)
    if not minimum_words <= word_count <= maximum_words:
        raise ValueError(
            f"Transcript needs {minimum_words}-{maximum_words} words for the selected duration."
        )

    script = " ".join(paragraphs).lower()
    analytical_frames = (
        "what stands out here",
        "this presentation looks at",
        "this slide feels like",
        "what's happening here",
        "what is happening here",
        "this behavior gives us",
        "the observation is simple",
        "was directly observed",
        "the participant kept",
    )
    if any(frame in script for frame in analytical_frames):
        raise ValueError(
            "Transcript reads like slide analysis instead of words a presenter can say."
        )

    repeated_scaffolding = (
        "this matters because",
        "that matters because",
        "that is why",
        "that's why",
        "from here",
        "the key point is",
        "the main takeaway is",
    )
    scaffold_uses = sum(script.count(frame) for frame in repeated_scaffolding)
    if scaffold_uses > 2:
        raise ValueError("Transcript relies too heavily on repeated explanatory transitions.")
    return paragraphs


def _script_analysis_prompt(paragraphs: list[str], source_context: dict | None = None) -> str:
    script = "\n\n".join(paragraphs)
    required_acronyms = _required_acronyms(paragraphs)
    grounding_context = (
        json.dumps(source_context, ensure_ascii=False)
        if source_context is not None
        else "Not supplied. Return an empty grounding_issues array."
    )
    return f"""You are a presentation coach reviewing a spoken presenter script. Use only the script provided. Return strict JSON only.

SCRIPT:
{script}

COMPLEX TERMS:
Identify terminology that is not ordinary day-to-day language for a general audience. Include acronyms and abbreviations, technical or academic terminology, industry jargon, specialized business metrics, and uncommon domain-specific words or phrases. Every acronym listed under MANDATORY ACRONYMS must appear in complex_terms, even when its full form is written nearby; the definition can simply reinforce that explanation. Do not treat a term as ordinary merely because its meaning can be inferred from context. Product and feature names are not automatically complex unless they contain specialized terminology. Ordinary words such as feedback, partnership, recruitment, skills, profile, and matching are not complex by themselves. Widely understood AI is the only acronym excluded automatically. A longer phrase and a word contained inside it are one term, not two. Return at most eight terms, prioritizing mandatory acronyms and the terminology most useful to explain aloud. For each term, provide a concise plain-English definition and use only ordinary English letters in the pronunciation guide.

MANDATORY ACRONYMS:
{json.dumps(required_acronyms, ensure_ascii=False)}

TONE CHECK:
Classify the script's primary DELIVERY tone as exactly one of Persuasive, Informative, Aggressive, Neutral, or Conversational. Judge how the language sounds, not merely what subject it explains. A script can explain information and still be Conversational when it consistently uses direct audience language, contractions, shorter spoken sentences, and relaxed transitions. Use Informative when neutral explanation is the dominant delivery. Use Persuasive when the language actively builds a supported position or recommendation. Use Aggressive only for combative, pressuring, or hostile delivery, and Neutral when no stronger tone is present. Give a confidence from 0 to 1 and one sentence grounded in the script. Do not label a tone as bad merely because it is not persuasive.

VOCABULARY UPGRADES:
Suggest no more than two targeted improvements, and only when the original has a specific problem: unclear meaning, unnecessary length, noticeable repetition, language too casual for the selected script, or language too formal to say naturally. Label that exact problem. Quote an exact phrase that appears in the script. The replacement must preserve the strength and certainty of the original claim. Do not introduce claims of accuracy, effectiveness, improvement, trust, speed, reliability, or better outcomes unless those claims already exist in the original phrase. Do not suggest a synonym merely because it sounds smoother or more sophisticated, replace one cliche with another, remove a harmless dash, or optimize an Informative script toward Conversational delivery. Return an empty array when the wording is already suitable; an empty array is preferred to a minor preference.

GROUNDING CHECK:
Compare the script with the supplied source context. Report only concrete claims, interpretations, numbers, relationships, or descriptions that are not supported by that context. Never add an item merely to say that a statement is supported or that there is no issue. A direct restatement of visible labels or straightforward arithmetic explicitly shown by the slide's values and percentage label is supported. Content from another slide may be used only as a clearly framed preview or transition; it must not be presented as though it appears on the current slide. Never assign a meaning to a name, identifier, team label, acronym, decorative element, or image unless the source context supports that meaning. Treat plausible benefits as unsupported unless stated: for example, that imported data is better, a score creates trust, feedback improves a system over time, results are grounded in outcomes, a process is more accurate, or a market is large enough to matter. An inference is unsupported when the source merely makes it plausible. Also check proposed vocabulary replacements and report any replacement that strengthens or adds a claim. Return at most four distinct, material issues, with no duplicates or near-duplicates. Return an empty array when everything is grounded.

SOURCE CONTEXT:
{grounding_context}

Return exactly:
{{
  "complex_terms": [{{"term":"string","definition":"string","pronunciation":"ordinary English letters","why_complex":"why context does not already explain it"}}],
  "tone_check": {{"classification":"Persuasive|Informative|Aggressive|Neutral|Conversational","confidence":0.0,"rationale":"string"}},
  "vocabulary_upgrades": [{{"original":"exact phrase from script","suggested":"string","reason":"specific improvement","issue":"unclear|wordy|repetitive|too-casual|too-formal"}}],
  "grounding_issues": ["specific unsupported statement"]
}}"""


def analyze_script(paragraphs: list[str], source_context: dict | None = None) -> dict:
    result = _request_json(_script_analysis_prompt(paragraphs, source_context), max_tokens=1400)
    try:
        parsed = ScriptAnalysis.model_validate(result)
    except ValidationError as error:
        logger.error(
            "Transcript coaching response failed schema validation: %s; response=%s",
            error,
            json.dumps(result, ensure_ascii=False)[:12000],
        )
        raise ValueError(
            "Transcript coaching response did not match the required schema."
        ) from error
    script_text = _normalized_phrase(" ".join(paragraphs))
    complex_terms = [
        {
            "term": item.term.strip(),
            "definition": item.definition.strip(),
            "pronunciation": item.pronunciation.strip(),
        }
        for item in parsed.complex_terms
        if _normalized_phrase(item.term) in script_text
        and _normalized_phrase(item.term) not in NON_COMPLEX_TERMS
        and item.pronunciation.isascii()
    ]
    returned_terms = {_normalized_phrase(item["term"]) for item in complex_terms}
    for acronym in _required_acronyms(paragraphs):
        if _normalized_phrase(acronym) in returned_terms:
            continue
        complex_terms.append(
            {
                "term": acronym,
                "definition": "An abbreviation used in this script that should be expanded or explained for the audience.",
                "pronunciation": _acronym_pronunciation(acronym),
            }
        )
    complex_terms = complex_terms[:8]
    vocabulary_upgrades = [
        {
            "original": item.original.strip(),
            "suggested": item.suggested.strip(),
            "reason": item.reason.strip(),
        }
        for item in parsed.vocabulary_upgrades
        if _normalized_phrase(item.original) in script_text
        and _normalized_phrase(item.original) != _normalized_phrase(item.suggested)
        and "slight" not in item.reason.casefold()
        and not _adds_stronger_claim(item.original, item.suggested)
    ][:2]
    grounding_issues: list[str] = []
    seen_grounding_issues: set[str] = set()
    for issue in parsed.grounding_issues:
        cleaned = issue.strip()
        normalized = _normalized_phrase(cleaned)
        if not cleaned or normalized in seen_grounding_issues:
            continue
        if "no issue" in normalized or "is supported" in normalized:
            continue
        seen_grounding_issues.add(normalized)
        grounding_issues.append(cleaned)
        if len(grounding_issues) == 4:
            break
    return {
        "complex_terms": complex_terms,
        "tone_check": parsed.tone_check.model_dump(),
        "vocabulary_upgrades": vocabulary_upgrades,
        "grounding_issues": grounding_issues,
    }


def generate_script(
    slide: dict,
    duration_seconds: int,
    tone: Tone,
    style: Style,
    previous_slide: dict | None = None,
    next_slide: dict | None = None,
    deck_slides: list[dict] | None = None,
    audience_level: AudienceLevel = "general",
) -> dict:
    target_words, minimum_paragraphs, maximum_paragraphs, minimum_words = _script_shape(
        duration_seconds
    )
    prompt = f"""You write presenter notes for a university student. Your output is a speaker-ready talk track: the exact words a presenter can stand up and say aloud while this slide is on screen. This is NOT slide analysis, a research summary, or a description for somebody reading the deck later.

Use only the supplied deck context. Never invent a product, team, result, participant action, finding, audience, or claim.

SPEAKER-READY RULES:
- Write from the presenter's viewpoint. Use "I" for an individual project or reflection and "we" for team work when the slide supports it. Direct audience language such as "let's" is also natural.
- Explain why the point matters; do not describe the slide from outside it.
- Every sentence must be natural to say aloud. Write connected spoken English, not notes, captions, or bullet commentary.
- Do not use analytical frames such as "What stands out here", "This presentation looks at", "This slide feels like", "What is happening here", "The observation is", "This behavior gives us", or "The participant kept".
- Do not open with "In this slide", "Now we will discuss", "As you can see", "Moving on to", or filler such as "So basically".
- Do not read visible bullet points verbatim. Interpret them in plain spoken language.
- Do not make the presenter sound like an outside observer of their own work.
- Preserve uncertainty where the slide itself is exploratory or reflective. Do not overclaim.
- Treat the current slide as the primary source. Use adjacent slides and the deck outline only for a brief preview or transition.
- Do not claim that adjacent-slide information is visible on the current slide.
- Do not interpret unexplained names, identifiers, team labels, decorative graphics, or acronyms. Mention them only as labels when necessary.
- Do not infer chart values, trends, causes, or conclusions unless the supplied text or visual context explicitly states them.
- When the current slide is a cover or contains very little text, introduce the supported deck topic and roadmap instead of inventing meaning for its design or labels.
- Prefer concrete supported language over broad claims such as "the system is broken," "the issue is structural," or "this proves" unless the source says so.
- Do not add plausible product benefits as facts. Imported data is not automatically better, scores do not automatically create trust, feedback does not automatically improve results, and a numbered market is not automatically large enough to matter.
- Vary paragraph openings and transitions. Do not repeatedly rely on "This matters because," "That is why," "From here," or "The key point is."

STRUCTURE:
- Write exactly {minimum_paragraphs}-{maximum_paragraphs} paragraphs, each a complete spoken thought.
- Start with a direct opening or a natural bridge from the previous slide when one is available.
- Develop the slide's main point with enough explanation for a listener who cannot read every detail.
- End with a take-away or a bridge toward the next slide when the next context supports one.

GENERATION SETTINGS:
- Target duration: about {duration_seconds} seconds, approximately {target_words} words.
- Required length: {minimum_words}-{round(target_words * 1.2)} words.
- Target tone: {tone}.
- Tone rules: {TONE_RULES[tone]}
- Style: {style}.
- Style rules: {STYLE_RULES[style]}
- Audience knowledge level: {audience_level}.
- Explanation rules: {AUDIENCE_RULES[audience_level]}
- Audience level controls explanation depth, not tone, presentation purpose, or factual certainty. Preserve source meaning and the requested duration; prioritize main ideas instead of padding or rushing.
- The target tone controls the delivery and takes priority when tone and style create tension.

ADJACENT DECK CONTEXT:
Previous slide: {json.dumps(_neighbor_summary(previous_slide), ensure_ascii=False)}
Current slide: {_slide_context(slide)}
Next slide: {json.dumps(_neighbor_summary(next_slide), ensure_ascii=False)}

DECK OUTLINE FOR ORIENTATION ONLY:
{json.dumps(_deck_outline(deck_slides), ensure_ascii=False)}

Return strict JSON only:
{{"paragraphs":["speaker-ready paragraph", "speaker-ready paragraph"]}}"""

    last_error: ValueError | None = None
    best_fallback_result: dict | None = None
    best_fallback_score: tuple[int, int] | None = None
    for attempt in range(3):
        retry_instruction = ""
        if attempt:
            retry_instruction = (
                "\n\nYour previous draft was rejected because it did not meet the speaker-ready "
                f"requirements: {last_error}. Return a completely corrected transcript."
            )
        try:
            generated = _validate_spoken_script(
                _request_json(prompt + retry_instruction), duration_seconds
            )
            analysis = analyze_script(
                generated,
                {
                    "current_slide": json.loads(_slide_context(slide)),
                    "previous_slide": _neighbor_summary(previous_slide),
                    "next_slide": _neighbor_summary(next_slide),
                    "deck_outline": _deck_outline(deck_slides),
                },
            )
            complete_result = {"paragraphs": generated, **analysis}
            grounding_issues = analysis.get("grounding_issues", [])
            detected_tone = str(analysis["tone_check"]["classification"]).casefold()
            tone_matches = tone == "auto" or detected_tone == tone
            fallback_score = (-len(grounding_issues), int(tone_matches))
            if best_fallback_score is None or fallback_score > best_fallback_score:
                best_fallback_result = complete_result
                best_fallback_score = fallback_score
            if grounding_issues:
                last_error = ValueError(
                    "Unsupported or misattributed content: " + "; ".join(grounding_issues)
                )
                continue
            if tone_matches:
                return complete_result
            last_error = ValueError(
                f"Requested {tone} delivery, but the draft was classified as {detected_tone}."
            )
        except ValueError as error:
            last_error = error
            logger.warning(
                "Transcript generation attempt %s of 3 rejected for slide %s: %s",
                attempt + 1,
                slide.get("num"),
                error,
            )
    if best_fallback_result is not None:
        logger.warning(
            "Transcript generation used the best valid fallback for slide %s after retries: %s",
            slide.get("num"),
            last_error,
        )
        return best_fallback_result
    logger.error(
        "Transcript generation exhausted all attempts for slide %s: %s",
        slide.get("num"),
        last_error,
    )
    raise ValueError("Transcript generation failed speaker-ready validation after three attempts.")


def enhance_selection(
    slide: dict,
    selected_parts: list[str],
    tone: Tone,
    style: Style,
    audience_level: AudienceLevel = "general",
) -> list[str]:
    if not selected_parts or any(not part.strip() for part in selected_parts):
        raise ValueError("Transcript enhancement needs non-empty selected text.")

    prompt = f"""You are an expert presentation coach performing a precise edit to selected text from a presenter script. Return only JSON.

Preserve the selected text's factual meaning, voice, and point of view. Improve grammar, spoken rhythm, concision, and clarity. Follow the requested tone and style without making it stiff or adding claims that are not supported by the selected text or slide context.

The selection spans {len(selected_parts)} presenter-script paragraph(s). Return exactly {len(selected_parts)} replacement paragraph(s), in the same order. Each output item replaces only its matching input item. Do not merge, split, add, remove, or reorder paragraphs.

TARGET TONE: {tone}
STYLE: {style}
AUDIENCE KNOWLEDGE LEVEL: {audience_level}
EXPLANATION RULES: {AUDIENCE_RULES[audience_level]}
Apply this level only within the selected text. Do not assume the rest of the script has changed. Preserve meaning and paragraph boundaries.
SELECTED PARTS BY PARAGRAPH:
{json.dumps(selected_parts, ensure_ascii=False)}

SLIDE CONTEXT:
{_slide_context(slide)}

Return exactly: {{"replacement_paragraphs":["string"]}}"""
    result = _request_json(prompt, max_tokens=1000)
    try:
        replacements = [
            paragraph.strip()
            for paragraph in SelectionEnhancement.model_validate(result).replacement_paragraphs
        ]
    except ValidationError as error:
        raise ValueError(
            "Transcript enhancement response did not match the required schema."
        ) from error
    if len(replacements) != len(selected_parts) or any(not paragraph for paragraph in replacements):
        raise ValueError(
            "Transcript enhancement must preserve the selected paragraph structure."
        )
    return replacements
