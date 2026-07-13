"""LIVE persona summary (Phase 5.2 slice 2).

Uses the REAL qwen3:4b model to compress verified facts. Whatever the
model returns, the result is factually consistent: either a validated
model summary (used_model=True) or the deterministic template fallback —
never an invented number and never banned filler. Skips when the model is
not pulled.
"""

import json
import urllib.error
import urllib.request

import pytest

from thoth_daemon.core.persona import ResponseFact, ResponseIntent, ResponseMode
from thoth_daemon.core.persona_summary import FactualConsistencyValidator, PersonaSummaryComposer
from thoth_daemon.inference import LlamaCppInferenceProvider

ENDPOINT = "http://127.0.0.1:11434"
MODEL = "qwen3:4b"


def _available() -> bool:
    try:
        with urllib.request.urlopen(f"{ENDPOINT}/api/tags", timeout=3) as resp:  # noqa: S310
            tags = json.loads(resp.read().decode())
        return any(m.get("name", "").startswith(MODEL) for m in tags.get("models", []))
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


pytestmark = pytest.mark.skipif(not _available(), reason=f"{MODEL} not pulled")


async def test_live_summary_is_factually_consistent() -> None:
    fact = ResponseFact(
        intent=ResponseIntent.VERIFIED_COMPLETION,
        verified=True,
        succeeded_items=[
            "The daemon and desktop are running",
            "Both health checks passed",
            "Four files are modified",
        ],
    )
    provider = LlamaCppInferenceProvider(model=MODEL, endpoint=ENDPOINT)
    composer = PersonaSummaryComposer()
    r = await composer.compose(fact, provider, mode=ResponseMode.STANDARD)

    # Whichever path was taken, the output must be factually consistent and
    # free of hallucinated numbers / filler (validator would raise otherwise).
    FactualConsistencyValidator().validate(r.display.text, fact, max_chars=480)
    assert r.display.text
    assert "certainly" not in r.display.text.lower()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v", "-s"]))
