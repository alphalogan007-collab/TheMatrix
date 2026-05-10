"""
MindLayer — base class for all MindAI pipeline layers.

Mirrors existence_lab Layer interface exactly:
  - name: str attribute
  - on_reset(ctx): optional pre-pipeline setup
  - on_step(ctx):  main per-tick logic

Invariants (enforced by convention, not runtime checks):
  - State NEVER lives inside the layer object — only in ctx.identity.* / ctx.cache.*
  - Layers NEVER import or call each other — communicate only through ctx
  - Layers NEVER raise exceptions that propagate — catch internally, log, degrade gracefully
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.identity_context import IdentityContext


class MindLayer(ABC):
    """Abstract base for all pipeline layers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    def on_reset(self, ctx: IdentityContext) -> None:
        """Called once before on_step(). Override for setup/teardown."""

    @abstractmethod
    def on_step(self, ctx: IdentityContext) -> None:
        """Execute this layer's logic. Mutates ctx.identity and/or ctx.cache."""
