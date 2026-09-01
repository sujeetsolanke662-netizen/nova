"""FastAPI entrypoint for NOVA's backend service.

Wires the guardrails, apt-clutter scanner, and audit log modules up as HTTP
endpoints. Started via `uvicorn backend.app.main:app` - see
packaging/systemd/nova.service, which assumes this exact module path.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from . import audit_log
from .apt_clutter import scan_apt_clutter
from .guardrails import (
    PROTECTED,
    classify_path,
    is_protected,
    load_protected_patterns,
)
from ..config.settings import Settings, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    # Loaded once at boot rather than per-request - is_protected() and
    # classify_path() both just take this list as an argument, they don't
    # reload the YAML themselves.
    app.state.protected_patterns = load_protected_patterns(settings.protected_paths_config)
    yield


app = FastAPI(title="NOVA", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/guardrails/check")
def guardrails_check(path: str) -> dict[str, object]:
    settings: Settings = app.state.settings
    patterns = app.state.protected_patterns

    # This is read-only inspection - "would this path be blocked?" - not a
    # real enforcement decision, so log=False MUST stay explicit here.
    # is_protected()/classify_path() only write a "guardrail_block" audit
    # entry when log=True; if this endpoint ever gets "fixed" back to
    # logging, every poll of this endpoint (including repeated checks of
    # the same protected path) would fabricate audit entries for actions
    # NOVA never actually took. Real enforcement call sites (e.g. the
    # recommendation engine deciding whether to act on a file) are the
    # ones that should pass log=True - see the TODO at the top of
    # guardrails.py.
    classification = classify_path(path, patterns, settings.scan_roots, log=False)

    reason = None
    if classification == PROTECTED:
        _, reason = is_protected(path, patterns, log=False)

    return {"path": path, "classification": classification, "reason": reason}


@app.get("/api/apt-clutter/scan")
def apt_clutter_scan() -> list[dict]:
    return scan_apt_clutter()


@app.get("/api/audit-log")
def get_audit_log() -> list[dict]:
    settings: Settings = app.state.settings
    return audit_log.read_log(log_path=settings.audit_log_path)


@app.get("/api/audit-log/verify")
def verify_audit_log() -> dict[str, object]:
    settings: Settings = app.state.settings
    valid, broken_at_entry = audit_log.verify_chain(log_path=settings.audit_log_path)
    return {"valid": valid, "broken_at_entry": broken_at_entry}
