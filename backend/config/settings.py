"""Runtime configuration for NOVA's backend.

Centralizes the paths that differ from machine to machine (where to scan,
where the protected-paths config and audit log live) so main.py and the
modules it wires up never hardcode them inline. Every field can be
overridden via an environment variable, which is the intended way to point
this at the actual demo machine's directories later without touching code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..app.audit_log import DEFAULT_LOG_PATH
from ..app.forecasting import DEFAULT_SNAPSHOT_LOG
from ..app.quarantine import DEFAULT_MANIFEST_PATH, DEFAULT_QUARANTINE_DIR

_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _default_scan_roots() -> list[str]:
    env = os.environ.get("NOVA_SCAN_ROOTS")
    if env:
        return [p for p in env.split(":") if p]
    return [str(Path.home() / "Downloads")]


def _default_protected_paths_config() -> str:
    return os.environ.get(
        "NOVA_PROTECTED_PATHS_CONFIG",
        str(_BACKEND_DIR / "config" / "protected_paths.yaml"),
    )


def _default_audit_log_path() -> str:
    return os.environ.get("NOVA_AUDIT_LOG_PATH", str(DEFAULT_LOG_PATH))


def _default_quarantine_dir() -> str:
    return os.environ.get("NOVA_QUARANTINE_DIR", str(DEFAULT_QUARANTINE_DIR))


def _default_quarantine_manifest_path() -> str:
    return os.environ.get("NOVA_QUARANTINE_MANIFEST_PATH", str(DEFAULT_MANIFEST_PATH))


def _default_snapshot_log_path() -> str:
    return os.environ.get("NOVA_SNAPSHOT_LOG_PATH", str(DEFAULT_SNAPSHOT_LOG))


def _default_llm_model_path() -> str:
    return os.environ.get(
        "NOVA_LLM_MODEL_PATH",
        str(_BACKEND_DIR / "models" / "Llama-3.2-1B-Instruct-Q4_K_M.gguf"),
    )


def _default_llm_timeout_seconds() -> float:
    # The model now loads once at server startup (see main.py's lifespan
    # handler), so this only has to cover generation time, not load time -
    # observed clean generation was ~4.5s, so 12.0s leaves real margin
    # without resurrecting the old cold-load-eats-the-budget problem.
    return float(os.environ.get("NOVA_LLM_TIMEOUT_SECONDS", "12.0"))


@dataclass(frozen=True)
class Settings:
    scan_roots: list[str] = field(default_factory=_default_scan_roots)
    protected_paths_config: str = field(default_factory=_default_protected_paths_config)
    audit_log_path: str = field(default_factory=_default_audit_log_path)
    quarantine_dir: str = field(default_factory=_default_quarantine_dir)
    quarantine_manifest_path: str = field(default_factory=_default_quarantine_manifest_path)
    snapshot_log_path: str = field(default_factory=_default_snapshot_log_path)
    llm_model_path: str = field(default_factory=_default_llm_model_path)
    llm_timeout_seconds: float = field(default_factory=_default_llm_timeout_seconds)


def get_settings() -> Settings:
    """Build a fresh Settings from the current environment.

    Not cached: reading env vars is cheap, and re-reading on each call
    (rather than memoizing at import time) keeps tests free to monkeypatch
    the environment and get a Settings that reflects it.
    """
    return Settings()
