"""spoink task-creation pipeline — turn captured/sliced surfaces @ T into a runnable
agent-eval task (the preview-500s shape, generalized). Supports observability tasks
(investigate surfaces -> code fix, graded by tests) and integration tasks (operate the
clone tools -> graded by reading state back through the same APIs)."""
from .spec import Anchor, Surface, TaskSpec, VerifierSpec
from .generate import generate_task

__all__ = ["TaskSpec", "Surface", "Anchor", "VerifierSpec", "generate_task"]
