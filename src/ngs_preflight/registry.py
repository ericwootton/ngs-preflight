"""The check registry: one place that defines every check.

Each check is a small function registered with an ID, a severity, a title, a
plain-language message template, a technical detail, and a suggested fix. The
generated catalogue (``docs/checks.md``), ``preflight explain`` and the reports
all read from here, so documentation cannot drift from the code.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from ngs_preflight.models import Severity

Scope = Literal["bed", "samplesheet", "cross", "identity"]
CheckFunc = Callable[[Any], Iterable["Hit"]]


@dataclass(frozen=True)
class Hit:
    """What a check function yields: values to fill the templates, plus evidence."""

    params: Mapping[str, object] = field(default_factory=dict)
    file: str | None = None
    technical: str = ""
    severity: Severity | None = None


@dataclass(frozen=True)
class CheckSpec:
    id: str
    severity: Severity
    title: str
    message: str
    detail: str
    fix: str
    scope: Scope
    func: CheckFunc
    requires: tuple[str, ...] = ()
    notes: str = ""

    @property
    def group(self) -> str:
        return self.id.rstrip("0123456789")

    def render_message(self, params: Mapping[str, object]) -> str:
        return self.message.format(**params)

    def render_fix(self, params: Mapping[str, object]) -> str:
        return self.fix.format(**params)


REGISTRY: dict[str, CheckSpec] = {}


def check(
    *,
    id: str,
    severity: Severity,
    title: str,
    message: str,
    detail: str,
    fix: str,
    scope: Scope,
    requires: tuple[str, ...] = (),
    notes: str = "",
) -> Callable[[CheckFunc], CheckFunc]:
    """Register a check function. Raises if the ID is reused."""

    def decorator(func: CheckFunc) -> CheckFunc:
        if id in REGISTRY:
            raise ValueError(f"duplicate check id {id}")
        REGISTRY[id] = CheckSpec(
            id=id,
            severity=severity,
            title=title,
            message=message,
            detail=detail,
            fix=fix,
            scope=scope,
            func=func,
            requires=requires,
            notes=notes,
        )
        return func

    return decorator


def load_checks() -> dict[str, CheckSpec]:
    """Import the check modules (registering them) and return the registry."""
    from ngs_preflight.checks import (  # noqa: F401
        bed_checks,
        identity_checks,
        reference_checks,
        samplesheet_checks,
    )

    return REGISTRY


def checks_for_scope(scope: Scope) -> list[CheckSpec]:
    return sorted((c for c in load_checks().values() if c.scope == scope), key=lambda c: c.id)


def get_check(check_id: str) -> CheckSpec | None:
    return load_checks().get(check_id.upper())


def all_checks() -> list[CheckSpec]:
    return sorted(load_checks().values(), key=lambda c: c.id)
