"""apt/dpkg clutter detector for NOVA.

Scans the system's package manager state (not arbitrary files) to surface
Linux-specific storage waste that a generic file scanner has no way to see:
packages apt would remove as orphaned dependencies, kernels superseded by a
newer install, cached .deb files for versions that are no longer installed,
and residual config left behind by packages that were removed but not purged.

Every check shells out to `apt`/`apt-get`/`dpkg`/`uname` and parses their
real output rather than guessing at state, and nothing here ever mutates
the system - these are read-only queries (`--dry-run` / `-l` / `-W`), never
`apt-get remove` or similar.
"""

from __future__ import annotations

import functools
import re
import subprocess
from pathlib import Path

from . import audit_log

DEFAULT_TIMEOUT = 30.0

CACHE_STALE = "stale_deb_cache"
CONFIG_ORPHANED = "orphaned_config_file"
KERNEL_OLD = "old_kernel"
PACKAGE_ORPHANED = "orphaned_package"


class AptQueryError(RuntimeError):
    """Raised when a shelled-out apt/dpkg/uname query fails or times out."""


def _run(args: list[str], timeout: float = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run a command safely (arg list, never shell=True) and return the result.

    Wraps genuine execution failures (missing binary, timeout, other OS-level
    errors) in AptQueryError. Does NOT check the return code - callers decide
    whether a non-zero exit is an error (`_run_strict`) or expected/benign
    (`_run_lenient`, `_compare_versions`).
    """
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise AptQueryError(f"Command timed out after {timeout}s: {' '.join(args)}") from e
    except OSError as e:
        raise AptQueryError(f"Failed to run '{' '.join(args)}': {e}") from e


def _run_strict(args: list[str], timeout: float = DEFAULT_TIMEOUT) -> str:
    """Run a command and return stdout, raising AptQueryError on non-zero exit."""
    result = _run(args, timeout=timeout)
    if result.returncode != 0:
        raise AptQueryError(
            f"Command '{' '.join(args)}' exited with status {result.returncode}: "
            f"{result.stderr.strip()}"
        )
    return result.stdout


def _run_lenient(args: list[str], timeout: float = DEFAULT_TIMEOUT) -> str:
    """Run a command and return stdout even on non-zero exit.

    Used for `dpkg-query -W <pkg1> <pkg2> ...`: dpkg-query exits non-zero if
    ANY of several requested packages isn't found in its database, but still
    prints valid data on stdout for the ones that were found. That's not a
    real failure for our purposes, so we don't raise on it.
    """
    return _run(args, timeout=timeout).stdout


def _compare_versions(v1: str, op: str, v2: str) -> bool:
    """Compare two Debian package versions via `dpkg --compare-versions`.

    Delegates to dpkg rather than reimplementing Debian's version ordering
    (epochs, tildes, alphanumeric segments) by hand. Exit code 0 means the
    comparison holds, 1 means it doesn't - both are legitimate outcomes.
    Anything else (e.g. a malformed version string) is a real error.
    """
    result = _run(["dpkg", "--compare-versions", v1, op, v2])
    if result.returncode not in (0, 1):
        raise AptQueryError(
            f"dpkg --compare-versions failed comparing '{v1}' {op} '{v2}': "
            f"{result.stderr.strip()}"
        )
    return result.returncode == 0


# --- dpkg -l parsing (shared by old_kernels, stale_deb_cache, orphaned_config_files) ---

# Data lines look like:
#   ii  adduser        3.118        all      add and remove users and groups
#   rc  old-package    1.2.3-1      amd64    an old package
# The header/separator lines (`Desired=...`, `| Status=...`, `+++-===...`)
# never match: they don't have two letters followed by whitespace in that
# position.
_DPKG_L_RE = re.compile(
    r"^(?P<status>[a-zA-Z]{2})\s+(?P<name>\S+)\s+(?P<version>\S+)\s+(?P<arch>\S+)\s+(?P<description>.*)$"
)


def _parse_dpkg_l(output: str) -> list[dict]:
    entries = []
    for line in output.splitlines():
        m = _DPKG_L_RE.match(line)
        if m:
            entries.append(m.groupdict())
    return entries


def _is_currently_installed(status: str) -> bool:
    """True for dpkg statuses meaning the package is actually on disk now.

    The second status character is the "Status" field: 'i' = installed.
    Covers "ii" (install/installed) and "hi" (hold/installed); excludes
    "rc" (remove/config-files-remain) and "un" (unknown/not installed).
    """
    return len(status) == 2 and status[1] == "i"


def _installed_versions_by_name(entries: list[dict]) -> dict[str, str]:
    return {
        e["name"].split(":", 1)[0]: e["version"]
        for e in entries
        if _is_currently_installed(e["status"])
    }


def _installed_sizes_bytes(package_names: list[str]) -> dict[str, int]:
    """Look up installed size (in bytes) per package via `dpkg-query -W`."""
    if not package_names:
        return {}
    output = _run_lenient(
        ["dpkg-query", "-W", "-f", "${Package} ${Installed-Size}\n", *package_names]
    )
    sizes: dict[str, int] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            sizes[parts[0]] = int(parts[1]) * 1024
    return sizes


# --- orphaned_packages ---

_APT_LIST_RE = re.compile(
    r"^(?P<name>\S+)/(?P<suite>\S+)\s+(?P<version>\S+)\s+(?P<arch>\S+)\s+\[(?P<flags>[^\]]*)\]"
)
_AUTOREMOVE_HEADER_RE = re.compile(r"^The following packages will be REMOVED:")


def _parse_apt_list_installed(output: str) -> set[str]:
    names = set()
    for line in output.splitlines():
        m = _APT_LIST_RE.match(line)
        if m:
            names.add(m.group("name").split(":", 1)[0])
    return names


def _parse_autoremove_candidates(output: str) -> list[str]:
    """Pull package names out of apt-get's "will be REMOVED" block.

    The block is a header line followed by one or more indented, wrapped
    lines of space-separated package names, ending at the first line that
    isn't indented (or end of output).
    """
    names: list[str] = []
    in_block = False
    for line in output.splitlines():
        if _AUTOREMOVE_HEADER_RE.match(line):
            in_block = True
            continue
        if not in_block:
            continue
        if not line.strip():
            continue
        if line[0].isspace():
            names.extend(line.split())
        else:
            break
    return names


def orphaned_packages() -> list[dict]:
    """Packages installed as dependencies that nothing depends on anymore.

    Cross-references `apt-get autoremove --dry-run`'s removal candidates
    against `apt list --installed` so we only ever report packages apt
    itself currently considers installed. Nothing is actually removed.
    """
    installed_names = _parse_apt_list_installed(_run_strict(["apt", "list", "--installed"]))
    candidates = _parse_autoremove_candidates(
        _run_strict(["apt-get", "autoremove", "--dry-run"])
    )
    candidates = [name for name in candidates if name in installed_names]

    sizes = _installed_sizes_bytes(candidates)

    return [
        {
            "category": PACKAGE_ORPHANED,
            "description": (
                f"'{name}' was installed as a dependency but is no longer required by any "
                "installed package (apt-get autoremove candidate)."
            ),
            "estimated_size_bytes": sizes.get(name, 0),
            "safe_to_auto_apply": False,
            "target_paths": [name],
        }
        for name in candidates
    ]


# --- old_kernels ---

_KERNEL_NAME_RE = re.compile(r"^linux-image-\d")


def old_kernels() -> list[dict]:
    """Installed linux-image-* packages other than running + most recent.

    The currently running kernel (from `uname -r`) and the newest installed
    kernel (by Debian version comparison, via dpkg) are never flagged, even
    if apt-get autoremove would consider one of them removable.
    """
    running_release = _run_strict(["uname", "-r"]).strip()
    running_pkg_name = f"linux-image-{running_release}"

    entries = _parse_dpkg_l(_run_strict(["dpkg", "-l"]))
    kernels = [
        e
        for e in entries
        if _is_currently_installed(e["status"]) and _KERNEL_NAME_RE.match(e["name"])
    ]
    if not kernels:
        return []

    newest = functools.reduce(
        lambda a, b: a if _compare_versions(a["version"], "gt", b["version"]) else b,
        kernels,
    )

    old = [k for k in kernels if k["name"] != running_pkg_name and k["name"] != newest["name"]]

    sizes = _installed_sizes_bytes([k["name"] for k in old])

    return [
        {
            "category": KERNEL_OLD,
            "description": (
                f"'{k['name']}' (version {k['version']}) is an installed kernel that is "
                "neither the currently running kernel nor the most recently installed one."
            ),
            "estimated_size_bytes": sizes.get(k["name"], 0),
            "safe_to_auto_apply": False,
            "target_paths": [k["name"]],
        }
        for k in old
    ]


# --- stale_deb_cache ---

# apt cache filenames: <name>_<version>_<arch>.deb, with ':' (epoch
# separator) escaped as '%3a' since ':' isn't safe in a filename.
_DEB_FILENAME_RE = re.compile(r"^(?P<name>[^_]+)_(?P<version>.+)_(?P<arch>[^_.]+)\.deb$")


def _unescape_deb_version(version: str) -> str:
    return version.replace("%3a", ":").replace("%3A", ":")


def stale_deb_cache(cache_dir: str = "/var/cache/apt/archives") -> list[dict]:
    """Leftover .deb files whose version doesn't match what's installed.

    Flags cache files for packages that are no longer installed at all, or
    whose installed version has since changed, per `dpkg -l`.
    """
    installed_versions = _installed_versions_by_name(_parse_dpkg_l(_run_strict(["dpkg", "-l"])))

    cache_path = Path(cache_dir)
    if not cache_path.is_dir():
        return []

    findings = []
    for deb_file in sorted(cache_path.glob("*.deb")):
        m = _DEB_FILENAME_RE.match(deb_file.name)
        if not m:
            continue

        name = m.group("name")
        version = _unescape_deb_version(m.group("version"))
        installed_version = installed_versions.get(name)

        if installed_version == version:
            continue  # matches the currently installed version - keep it

        if installed_version is None:
            reason = f"package '{name}' is no longer installed"
        else:
            reason = f"installed version is '{installed_version}', not '{version}'"

        try:
            size_bytes = deb_file.stat().st_size
        except OSError:
            continue

        findings.append(
            {
                "category": CACHE_STALE,
                "description": (
                    f"Cached package file '{deb_file.name}' is stale ({reason}) and can be "
                    "safely removed from the apt cache."
                ),
                "estimated_size_bytes": size_bytes,
                "safe_to_auto_apply": True,
                "target_paths": [str(deb_file)],
            }
        )
    return findings


# --- orphaned_config_files ---


def orphaned_config_files() -> list[dict]:
    """Residual config from packages that were removed but not purged.

    dpkg reports these as status "rc" (remove/config-files-remain) in
    `dpkg -l`: the package itself is gone, but its conffiles are still
    sitting on disk.
    """
    entries = _parse_dpkg_l(_run_strict(["dpkg", "-l"]))
    residual = [e for e in entries if e["status"] == "rc"]

    sizes = _installed_sizes_bytes([e["name"] for e in residual])

    return [
        {
            "category": CONFIG_ORPHANED,
            "description": (
                f"'{e['name']}' was removed but its configuration files remain on disk "
                "(dpkg status 'rc')."
            ),
            "estimated_size_bytes": sizes.get(e["name"], 0),
            "safe_to_auto_apply": True,
            "target_paths": [e["name"]],
        }
        for e in residual
    ]


def scan_apt_clutter() -> list[dict]:
    """Run every apt/dpkg clutter check and return the combined findings.

    Each finding already carries its own 'category' (see the individual
    check functions); this just aggregates them. Any AptQueryError from an
    underlying check propagates rather than being swallowed, so a broken
    apt/dpkg call surfaces clearly instead of silently reporting nothing.
    """
    findings: list[dict] = []
    findings.extend(orphaned_packages())
    findings.extend(old_kernels())
    findings.extend(stale_deb_cache())
    findings.extend(orphaned_config_files())

    for finding in findings:
        audit_log.append_entry(
            action_type="recommend",
            target_paths=finding.get("target_paths", []),
            reason=finding["description"],
        )

    return findings
