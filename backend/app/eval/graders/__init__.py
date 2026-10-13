"""Grader implementations. See :mod:`.base` for the shared interface and
:data:`.base.GRADER_REGISTRY` for the type -> instance mapping the runner uses."""

from .base import GRADER_REGISTRY, Grader, GradeContext, GradeResult

# Import every concrete grader module so it registers itself into GRADER_REGISTRY as a
# side effect of import. Order doesn't matter -- each module calls register() once at
# module scope.
from . import tool_calls as _tool_calls  # noqa: E402,F401
from . import budget as _budget  # noqa: E402,F401
from . import code_syntax as _code_syntax  # noqa: E402,F401
from . import json_schema as _json_schema  # noqa: E402,F401
from . import llm_judge as _llm_judge  # noqa: E402,F401
from . import string_match as _string_match  # noqa: E402,F401

__all__ = ["GRADER_REGISTRY", "Grader", "GradeContext", "GradeResult"]
