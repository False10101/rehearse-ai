"""Exercise the outbound feature payloads, not just a routing constant."""

import pytest

from app.services import (
    agenda_generator,
    gesture_coaching,
    slide_analyzer,
    speech_evidence,
    transcript_enhancer,
)


class RequestCaptured(BaseException):
    """Stop before response parsing, without triggering feature retries."""


@pytest.mark.parametrize("feature", ["slides", "transcript", "agenda", "speech", "gesture"])
def test_luna_features_prefer_fast_and_keep_the_existing_model(monkeypatch, feature):
    payloads = []

    def capture(*args, **kwargs):
        payloads.append(kwargs["json"])
        raise RequestCaptured()

    for module in (slide_analyzer, transcript_enhancer, agenda_generator):
        monkeypatch.setattr(module, "openrouter_headers", lambda: {})
    monkeypatch.setattr(slide_analyzer, "post_provider_request", capture)
    monkeypatch.setattr(transcript_enhancer, "post_provider_request", capture)
    monkeypatch.setattr(agenda_generator.requests, "post", capture)
    with pytest.raises(RequestCaptured):
        if feature == "slides":
            slide_analyzer.analyze([{"num": 1, "text": []}])
        elif feature == "agenda":
            agenda_generator._items_from_model([{"num": 1, "text": []}])
        else:
            # Speech and gesture wording import this actual request function.
            module = {"speech": speech_evidence, "gesture": gesture_coaching,
                      "transcript": transcript_enhancer}[feature]
            module._request_json("speaker-ready feedback", max_tokens=2200)
    payload = payloads[0]
    assert payload["model"] == "openai/gpt-6-luna"
    assert payload["service_tier"] == "priority"
    assert payload["provider"] == {"order": ["openai/fast"], "allow_fallbacks": True}
    assert payload["messages"]
    assert payload["response_format"]


def test_qwen_vision_does_not_inherit_luna_routing(monkeypatch, tmp_path):
    payloads = []

    def capture(*args, **kwargs):
        payloads.append(kwargs["json"])
        raise RequestCaptured()

    image = tmp_path / "slide.png"
    from PIL import Image
    Image.new("RGB", (800, 450)).save(image)
    monkeypatch.setattr(slide_analyzer, "post_provider_request", capture)
    monkeypatch.setattr(slide_analyzer, "openrouter_headers", lambda: {})
    with pytest.raises(RequestCaptured):
        slide_analyzer.caption_slide_image(1, image, "Source slide text")
    assert payloads[0]["model"] == "qwen/qwen3-vl-30b-a3b-instruct"
    assert payloads[0]["provider"] == {"order": ["deepinfra"], "allow_fallbacks": True}
    assert "service_tier" not in payloads[0]
