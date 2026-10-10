from app.services import agenda_generator, slide_analyzer, transcript_enhancer


def test_text_features_use_the_slide_analyzer_luna_model() -> None:
    assert slide_analyzer.ANALYSIS_MODEL == "openai/gpt-6-luna"
    assert transcript_enhancer.TRANSCRIPT_MODEL == slide_analyzer.ANALYSIS_MODEL
    assert agenda_generator.AGENDA_MODEL == slide_analyzer.ANALYSIS_MODEL
    assert slide_analyzer.VISION_MODEL == "qwen/qwen3-vl-8b-instruct"


def test_transcript_request_sends_luna(monkeypatch) -> None:
    payloads = []

    def post(*args, **kwargs):
        payloads.append(kwargs["json"])
        return object()

    monkeypatch.setattr(transcript_enhancer, "openrouter_headers", lambda: {})
    monkeypatch.setattr(transcript_enhancer.requests, "post", post)
    monkeypatch.setattr(transcript_enhancer, "_parse_json_content", lambda response: {})
    transcript_enhancer._request_json("test prompt")
    assert payloads[0]["model"] == "openai/gpt-6-luna"
