"""Opt-in semantic claim-support layer (non-deterministic; BYO backend).

Importing this subpackage is the explicit opt-in; the deterministic core never
imports it. See docs/superpowers/specs/2026-06-12-layered-architecture-design.md.
"""

from __future__ import annotations

from ghostcite.semantic.backends import (
    AnthropicBackend,
    OpenAICompatibleBackend,
    SemanticBackend,
    SemanticBackendError,
    build_backend,
)
from ghostcite.semantic.support import AbstractProvider, check_claim_support

__all__ = [
    "SemanticBackend",
    "SemanticBackendError",
    "OpenAICompatibleBackend",
    "AnthropicBackend",
    "build_backend",
    "AbstractProvider",
    "check_claim_support",
]
