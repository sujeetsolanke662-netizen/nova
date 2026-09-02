"""FastAPI entrypoint for NOVA's backend service.

Wires the guardrails, apt-clutter scanner, and audit log modules up as HTTP
endpoints. Started via `uvicorn backend.app.main:app` - see
packaging/systemd/nova.service, which assumes this exact module path.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import audit_log
from .apt_clutter import scan_apt_clutter
from .copilot_answer import answer_query, classify_query_intent, generate_answer
from .copilot_retrieval import build_index, search
from .forecasting import forecast_capacity, get_disk_usage, record_usage_snapshot
from .guardrails import (
    PROTECTED,
    REVIEWABLE,
    classify_path,
    is_protected,
    load_protected_patterns,
)
from .quarantine import QuarantineError, list_quarantined, quarantine_file, restore_file
from .recommendation import generate_recommendations
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

# The frontend (Vite dev server, or a static build served from its own
# origin) is always a different origin than this API, so without CORS
# headers every fetch() from it is blocked by the browser before this
# code even runs. Wide open is fine here: NOVA binds to 127.0.0.1 and
# this is a local trust tool, not a multi-tenant service with cookies
# to protect.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    classification = classify_path(
        path, patterns, settings.scan_roots, log=False, log_path=settings.audit_log_path
    )

    reason = None
    if classification == PROTECTED:
        _, reason = is_protected(path, patterns, log=False, log_path=settings.audit_log_path)

    return {"path": path, "classification": classification, "reason": reason}


def _validate_scan_root(root: str, patterns: list[dict], settings: Settings) -> Path:
    """Resolve `root` and confirm it's eligible to scan: it must exist as
    a directory, and must be REVIEWABLE per guardrails (neither protected
    nor outside every configured scan root). Raises HTTPException(400)
    otherwise - see /api/recommendations' original docstring reasoning for
    why this check exists at all (don't let these endpoints be used to
    scan arbitrary parts of the filesystem the user never configured).

    This is a read-only eligibility check, not the real enforcement
    decision - log=False, same reasoning as /api/guardrails/check. Any
    real per-file enforcement pass (log=True) happens inside
    generate_recommendations() itself.
    """
    root_path = Path(root).expanduser().resolve(strict=False)
    if not root_path.is_dir():
        raise HTTPException(status_code=400, detail=f"'{root}' is not an existing directory")

    classification = classify_path(
        str(root_path), patterns, settings.scan_roots, log=False, log_path=settings.audit_log_path
    )
    if classification != REVIEWABLE:
        if classification == PROTECTED:
            detail = f"'{root}' is a protected path and cannot be scanned"
        else:
            detail = f"'{root}' is outside all configured scan roots"
        raise HTTPException(status_code=400, detail=detail)

    return root_path


@app.get("/api/recommendations")
def get_recommendations(root: str) -> dict:
    settings: Settings = app.state.settings
    patterns = app.state.protected_patterns

    _validate_scan_root(root, patterns, settings)

    return generate_recommendations(
        root, settings.scan_roots, patterns, audit_log_path=settings.audit_log_path
    )


class QuarantineRequest(BaseModel):
    path: str
    reason: str


@app.post("/api/quarantine")
def quarantine(request: QuarantineRequest) -> dict:
    """Move a file into quarantine.

    quarantine_file() re-checks classify_path() itself (log=True) as the
    real enforcement point for this filesystem-changing action, so this
    endpoint is just a thin wire: it supplies the caller's path/reason
    plus the server's configured patterns/scan roots/paths and lets that
    function make (and log) the actual decision.
    """
    settings: Settings = app.state.settings
    patterns = app.state.protected_patterns

    try:
        return quarantine_file(
            request.path,
            request.reason,
            patterns,
            settings.scan_roots,
            quarantine_dir=settings.quarantine_dir,
            manifest_path=settings.quarantine_manifest_path,
            audit_log_path=settings.audit_log_path,
        )
    except QuarantineError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/quarantine/{quarantine_id}/restore")
def restore(quarantine_id: str) -> dict:
    settings: Settings = app.state.settings

    try:
        return restore_file(
            quarantine_id,
            manifest_path=settings.quarantine_manifest_path,
            audit_log_path=settings.audit_log_path,
        )
    except QuarantineError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/quarantine")
def get_quarantined() -> list[dict]:
    settings: Settings = app.state.settings
    return list_quarantined(manifest_path=settings.quarantine_manifest_path)


@app.get("/api/copilot/search")
def copilot_search(root: str, query: str, top_k: int = 10) -> list[dict]:
    settings: Settings = app.state.settings
    patterns = app.state.protected_patterns

    _validate_scan_root(root, patterns, settings)

    result = generate_recommendations(
        root, settings.scan_roots, patterns, audit_log_path=settings.audit_log_path
    )
    recommendations = result["recommendations"]
    if not recommendations:
        return []

    index = build_index(recommendations)
    return search(query, index, top_k=top_k)


class AskRequest(BaseModel):
    question: str
    root: str


@app.post("/api/copilot/ask")
def copilot_ask(request: AskRequest) -> dict:
    """The same scan -> index -> answer pipeline as `nova ask` (cli.py's
    _run_ask), just exposed over HTTP for the frontend instead of stdout.

    Returns generate_answer()'s shape directly: {"answer_text",
    "cited_paths", "intent"}. When there's nothing to search, this reuses
    generate_answer()'s own empty-results handling (still runs
    classify_query_intent so the returned "intent" is real, not a guess)
    rather than calling build_index() on an empty item list.
    """
    settings: Settings = app.state.settings
    patterns = app.state.protected_patterns

    _validate_scan_root(request.root, patterns, settings)

    result = generate_recommendations(
        request.root, settings.scan_roots, patterns, audit_log_path=settings.audit_log_path
    )
    recommendations = result["recommendations"]
    if not recommendations:
        return generate_answer(request.question, [], classify_query_intent(request.question))

    index = build_index(recommendations)
    return answer_query(request.question, index)


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


@app.get("/api/forecast")
def get_forecast(path: str) -> dict:
    """Live disk usage plus a capacity forecast for `path`, combined.

    `used_percent` etc. (from get_disk_usage) are always present - that's
    a live read, independent of history. The forecast fields depend on
    `status`: "ok" adds current_used_percent/trend_bytes_per_day/
    days_until_full (derived from recorded snapshots for this exact path
    string); "insufficient_data" adds snapshots_available/snapshots_needed
    instead of a fabricated projection - see forecasting.py.
    """
    settings: Settings = app.state.settings
    resolved = str(Path(path).expanduser())

    try:
        disk_usage = get_disk_usage(resolved)
    except OSError as e:
        raise HTTPException(
            status_code=400, detail=f"Could not read disk usage for '{path}': {e}"
        ) from e

    forecast = forecast_capacity(resolved, snapshot_log_path=settings.snapshot_log_path)

    return {**disk_usage, **forecast}


class SnapshotRequest(BaseModel):
    path: str


@app.post("/api/forecast/snapshot")
def record_forecast_snapshot(request: SnapshotRequest) -> dict:
    """Record a real, live usage snapshot for `path` right now.

    Reads actual current usage via get_disk_usage() rather than trusting
    the caller to supply used_bytes/total_bytes themselves - same reason
    generate_synthetic_history() does this, just for one real point
    instead of a synthetic backfill.
    """
    settings: Settings = app.state.settings
    resolved = str(Path(request.path).expanduser())

    try:
        disk_usage = get_disk_usage(resolved)
    except OSError as e:
        raise HTTPException(
            status_code=400, detail=f"Could not read disk usage for '{request.path}': {e}"
        ) from e

    return record_usage_snapshot(
        resolved,
        used_bytes=disk_usage["used_bytes"],
        total_bytes=disk_usage["total_bytes"],
        snapshot_log_path=settings.snapshot_log_path,
    )
