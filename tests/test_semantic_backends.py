import pytest

from ghostcite.models import SemanticVerdict
from ghostcite.semantic.backends import (
    AnthropicBackend,
    OpenAICompatibleBackend,
    SemanticBackendError,
    build_backend,
)

CLAIM = "Compound X cures disease Y."
ABSTRACT = "We studied compound X; it had no effect on disease Y."


def test_openai_backend_parses_verdict(httpx_mock):
    httpx_mock.add_response(
        url="http://local/v1/chat/completions",
        json={
            "choices": [
                {"message": {"content": '{"verdict": "unsupported", "rationale": "no effect"}'}}
            ]
        },
    )
    b = OpenAICompatibleBackend(base_url="http://local/v1", api_key=None, model="m")
    r = b.assess_support(CLAIM, ABSTRACT)
    assert r.verdict is SemanticVerdict.UNSUPPORTED
    assert r.rationale == "no effect"
    assert r.backend == "openai:m"


def test_openai_backend_sends_temperature_zero(httpx_mock):
    httpx_mock.add_response(
        url="http://local/v1/chat/completions",
        json={"choices": [{"message": {"content": '{"verdict": "supported", "rationale": "ok"}'}}]},
    )
    b = OpenAICompatibleBackend(base_url="http://local/v1", api_key="k", model="m")
    b.assess_support(CLAIM, ABSTRACT)
    req = httpx_mock.get_requests()[0]
    import json as _json

    body = _json.loads(req.content)
    assert body["temperature"] == 0
    assert body["model"] == "m"
    assert req.headers["authorization"] == "Bearer k"


def test_anthropic_backend_parses_verdict(httpx_mock):
    httpx_mock.add_response(
        url="https://api.anthropic.com/v1/messages",
        json={
            "content": [{"type": "text", "text": '{"verdict": "uncertain", "rationale": "vague"}'}]
        },
    )
    b = AnthropicBackend(api_key="k", model="claude-x")
    r = b.assess_support(CLAIM, ABSTRACT)
    assert r.verdict is SemanticVerdict.UNCERTAIN
    assert r.backend == "anthropic:claude-x"


def test_malformed_json_raises(httpx_mock):
    httpx_mock.add_response(
        url="http://local/v1/chat/completions",
        json={"choices": [{"message": {"content": "not json at all"}}]},
    )
    b = OpenAICompatibleBackend(base_url="http://local/v1", api_key=None, model="m")
    with pytest.raises(SemanticBackendError):
        b.assess_support(CLAIM, ABSTRACT)


def test_http_error_raises(httpx_mock):
    httpx_mock.add_response(url="http://local/v1/chat/completions", status_code=500)
    b = OpenAICompatibleBackend(base_url="http://local/v1", api_key=None, model="m")
    with pytest.raises(SemanticBackendError):
        b.assess_support(CLAIM, ABSTRACT)


def test_build_backend_openai_requires_base_url():
    with pytest.raises(SemanticBackendError):
        build_backend("openai", base_url=None, api_key=None, model="m")


def test_build_backend_anthropic_requires_key():
    with pytest.raises(SemanticBackendError):
        build_backend("anthropic", base_url=None, api_key=None, model="m")


def test_build_backend_unknown_kind():
    with pytest.raises(SemanticBackendError):
        build_backend("nope", base_url="x", api_key="y", model="m")
