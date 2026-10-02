"""Which ``Generator`` this process writes Sections with.

The ``Environment.LOCAL`` branch guards real Gemini spend, so the decision lives in
exactly one function that the app builds its ``RunDriver``'s generator provider from;
two call sites choosing for themselves is how a local run ends up paying for Gemini.
"""

from __future__ import annotations

from shell.adapters.gemini.generator import GeminiGenerator
from shell.adapters.local.generator import RecordedResponseGenerator
from shell.config import Environment, Settings
from shell.ports.generator import Generator

__all__ = ["generator_for_settings"]


def generator_for_settings(settings: Settings) -> Generator:
    """The ``Environment.LOCAL`` -> ``RecordedResponseGenerator()`` / else
    ``GeminiGenerator`` (built with the configured model) branch.

    ``settings.use_real_gemini_locally`` (Story 4.9's own opt-out) is the one
    exception: a developer who has explicitly set ``USE_REAL_GEMINI_LOCALLY``
    still gets a real ``GeminiGenerator`` under ``Environment.LOCAL`` --
    deliberate and explicit, never a deployment default."""
    if settings.environment is Environment.LOCAL and not settings.use_real_gemini_locally:
        return RecordedResponseGenerator()
    return GeminiGenerator(
        settings.gemini_api_key,
        model=settings.gemini_model,
        thinking_budget=settings.gemini_thinking_budget,
    )
