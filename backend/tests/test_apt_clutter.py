import subprocess

import pytest

from backend.app.apt_clutter import (
    AptQueryError,
    UnsafeApplyError,
    apply_finding,
    old_kernels,
    orphaned_config_files,
    orphaned_packages,
    scan_apt_clutter,
    stale_deb_cache,
)

APT_LIST_INSTALLED = """\
Listing... Done
accountsservice/stable,now 0.6.55-3 amd64 [installed,automatic]
acl/stable,now 2.2.53-10 amd64 [installed,automatic]
adduser/stable,now 3.118 all [installed]
libboost-filesystem1.71.0/stable,now 1.71.0-6ubuntu6.15 amd64 [installed,automatic]
libgtk-3-common/stable,now 3.24.20-0ubuntu1 all [installed,automatic]
python3-old-lib/stable,now 1.0.0-1 all [installed,automatic]
"""

AUTOREMOVE_DRY_RUN = """\
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
The following packages will be REMOVED:
  libboost-filesystem1.71.0 libgtk-3-common
  python3-old-lib
0 upgraded, 0 newly installed, 3 to remove and 0 not upgraded.
After this operation, 42.0 MB disk space will be freed.
"""

DPKG_L_HEADER = """\
Desired=Unknown/Install/Remove/Purge/Hold
| Status=Not/Inst/Conf-files/Unpacked/halF-conf/Half-inst/trig-aWait/Trig-pend
|/ Err?=(none)/Reinst-required (Status,Err: uppercase=bad)
||/ Name                        Version           Architecture Description
+++-===========================-=================-============-===================
"""

DPKG_L_KERNELS = (
    DPKG_L_HEADER
    + """\
ii  linux-image-5.10.0-7-amd64  5.10.40-1         amd64        Linux 5.10 for 64-bit PCs
ii  linux-image-5.10.0-8-amd64  5.10.46-4         amd64        Linux 5.10 for 64-bit PCs
ii  linux-image-5.10.0-9-amd64  5.10.50-1         amd64        Linux 5.10 for 64-bit PCs
ii  linux-image-amd64           5.10.50           amd64        Meta kernel package
"""
)

DPKG_L_FOR_CACHE = (
    DPKG_L_HEADER
    + """\
ii  adduser                     3.118             all          add and remove users and groups
ii  libboost-filesystem1.71.0   1.71.0-6ubuntu6.15 amd64       Boost filesystem library
rc  old-removed-package         1.2.3-1           amd64        an old package
"""
)

DPKG_L_WITH_RC = (
    DPKG_L_HEADER
    + """\
ii  adduser                     3.118             all          add and remove users and groups
rc  old-removed-package         1.2.3-1           amd64        an old package
rc  another-purged-thing        0.9-2             all          another old package
"""
)


def _completed(args, stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def _dpkg_query_output(pairs):
    return "".join(f"{name} {size_kb}\n" for name, size_kb in pairs)


class FakeRun:
    """Dispatches subprocess.run calls to canned responses based on argv.

    Each response is (predicate(args) -> bool, outcome), where outcome is a
    CompletedProcess, an Exception to raise, or a callable(args, **kwargs)
    that returns/raises one of those.
    """

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        for predicate, outcome in self.responses:
            if not predicate(args):
                continue
            if isinstance(outcome, Exception):
                raise outcome
            if callable(outcome) and not isinstance(outcome, subprocess.CompletedProcess):
                return outcome(args, **kwargs)
            return outcome
        raise AssertionError(f"No fake response registered for command: {args}")


def _install_fake_run(monkeypatch, responses):
    fake = FakeRun(responses)
    monkeypatch.setattr("backend.app.apt_clutter.subprocess.run", fake)
    return fake


@pytest.fixture(autouse=True)
def audit_calls(monkeypatch):
    """Capture audit_log.append_entry calls instead of touching real disk."""
    calls = []

    def fake_append_entry(**kwargs):
        calls.append(kwargs)
        return kwargs

    monkeypatch.setattr("backend.app.apt_clutter.audit_log.append_entry", fake_append_entry)
    return calls


def _starts_with(*prefix):
    prefix = list(prefix)
    return lambda args: list(args[: len(prefix)]) == prefix


# --- orphaned_packages ---


def test_orphaned_packages_parses_autoremove_and_apt_list(monkeypatch):
    responses = [
        (_starts_with("apt", "list", "--installed"), _completed(["apt"], stdout=APT_LIST_INSTALLED)),
        (
            _starts_with("apt-get", "autoremove", "--dry-run"),
            _completed(["apt-get"], stdout=AUTOREMOVE_DRY_RUN),
        ),
        (
            _starts_with("dpkg-query", "-W"),
            _completed(
                ["dpkg-query"],
                stdout=_dpkg_query_output(
                    [
                        ("libboost-filesystem1.71.0", 1200),
                        ("libgtk-3-common", 300),
                        ("python3-old-lib", 50),
                    ]
                ),
            ),
        ),
    ]
    _install_fake_run(monkeypatch, responses)

    findings = orphaned_packages()

    names = {f["description"] for f in findings}
    assert len(findings) == 3
    assert any("libboost-filesystem1.71.0" in d for d in names)
    assert any("libgtk-3-common" in d for d in names)
    assert any("python3-old-lib" in d for d in names)
    for f in findings:
        assert f["category"] == "orphaned_package"
        assert f["safe_to_auto_apply"] is False
        assert f["estimated_size_bytes"] > 0


def test_orphaned_packages_ignores_autoremove_names_not_in_apt_list(monkeypatch):
    # apt-get autoremove claims a package apt list --installed doesn't know
    # about (e.g. state drift) - it should be filtered out, not trusted blindly.
    autoremove_with_extra = AUTOREMOVE_DRY_RUN.replace(
        "  libboost-filesystem1.71.0 libgtk-3-common\n",
        "  libboost-filesystem1.71.0 libgtk-3-common ghost-package\n",
    )
    responses = [
        (_starts_with("apt", "list", "--installed"), _completed(["apt"], stdout=APT_LIST_INSTALLED)),
        (
            _starts_with("apt-get", "autoremove", "--dry-run"),
            _completed(["apt-get"], stdout=autoremove_with_extra),
        ),
        (_starts_with("dpkg-query", "-W"), _completed(["dpkg-query"], stdout="")),
    ]
    _install_fake_run(monkeypatch, responses)

    findings = orphaned_packages()

    assert all("ghost-package" not in f["description"] for f in findings)
    assert len(findings) == 3


# --- old_kernels ---


def test_old_kernels_excludes_running_and_newest_even_when_autoremove_would_flag_running(
    monkeypatch,
):
    # The running kernel (5.10.0-8) is deliberately NOT the newest installed
    # kernel (5.10.0-9) here - both must be excluded, only 5.10.0-7 flagged.
    def compare_versions(args, **kwargs):
        assert args[0:2] == ["dpkg", "--compare-versions"]
        v1, op, v2 = args[2], args[3], args[4]
        assert op == "gt"

        def parse(v):
            # e.g. "5.10.40-1" -> (40, 1)
            main, rev = v.split("-")
            return (float(main.split(".")[-1]), int(rev))

        result = 0 if parse(v1) > parse(v2) else 1
        return _completed(args, returncode=result)

    responses = [
        (_starts_with("uname", "-r"), _completed(["uname"], stdout="5.10.0-8-amd64\n")),
        (_starts_with("dpkg", "-l"), _completed(["dpkg"], stdout=DPKG_L_KERNELS)),
        (_starts_with("dpkg", "--compare-versions"), compare_versions),
        (
            _starts_with("dpkg-query", "-W"),
            _completed(
                ["dpkg-query"],
                stdout=_dpkg_query_output([("linux-image-5.10.0-7-amd64", 250000)]),
            ),
        ),
    ]
    _install_fake_run(monkeypatch, responses)

    findings = old_kernels()

    assert len(findings) == 1
    assert "linux-image-5.10.0-7-amd64" in findings[0]["description"]
    assert "linux-image-5.10.0-8-amd64" not in str(findings)  # running kernel excluded
    assert "linux-image-5.10.0-9-amd64" not in str(findings)  # newest kernel excluded
    assert findings[0]["category"] == "old_kernel"
    assert findings[0]["safe_to_auto_apply"] is False
    assert findings[0]["estimated_size_bytes"] == 250000 * 1024


def test_old_kernels_returns_empty_when_no_kernel_packages_installed(monkeypatch):
    responses = [
        (_starts_with("uname", "-r"), _completed(["uname"], stdout="5.10.0-8-amd64\n")),
        (_starts_with("dpkg", "-l"), _completed(["dpkg"], stdout=DPKG_L_HEADER)),
    ]
    _install_fake_run(monkeypatch, responses)

    assert old_kernels() == []


# --- stale_deb_cache ---


def test_stale_deb_cache_flags_removed_and_outdated_versions(monkeypatch, tmp_path):
    cache_dir = tmp_path / "archives"
    cache_dir.mkdir()

    # Matches installed version -> should NOT be flagged.
    current = cache_dir / "libboost-filesystem1.71.0_1.71.0-6ubuntu6.15_amd64.deb"
    current.write_bytes(b"0" * 1000)

    # Package no longer installed at all -> stale.
    removed = cache_dir / "old-removed-package_1.2.3-1_amd64.deb"
    removed.write_bytes(b"0" * 2048)

    # Package installed but at a different version -> stale.
    outdated = cache_dir / "adduser_3.100-1_all.deb"
    outdated.write_bytes(b"0" * 512)

    responses = [
        (_starts_with("dpkg", "-l"), _completed(["dpkg"], stdout=DPKG_L_FOR_CACHE)),
    ]
    _install_fake_run(monkeypatch, responses)

    findings = stale_deb_cache(cache_dir=str(cache_dir))

    flagged_files = {f["description"] for f in findings}
    assert len(findings) == 2
    assert any("old-removed-package" in d for d in flagged_files)
    assert any("adduser" in d for d in flagged_files)
    assert not any("libboost-filesystem1.71.0_1.71.0-6ubuntu6.15" in d for d in flagged_files)

    for f in findings:
        assert f["category"] == "stale_deb_cache"
        assert f["safe_to_auto_apply"] is True
        assert f["estimated_size_bytes"] > 0


def test_stale_deb_cache_handles_epoch_escaped_versions(monkeypatch, tmp_path):
    cache_dir = tmp_path / "archives"
    cache_dir.mkdir()

    deb_file = cache_dir / "somepkg_2%3a1.0-1_amd64.deb"
    deb_file.write_bytes(b"0" * 100)

    dpkg_l = DPKG_L_HEADER + "ii  somepkg                      2:1.0-1           amd64        pkg\n"
    responses = [(_starts_with("dpkg", "-l"), _completed(["dpkg"], stdout=dpkg_l))]
    _install_fake_run(monkeypatch, responses)

    # File version (unescaped "2:1.0-1") matches installed version exactly -> not stale.
    assert stale_deb_cache(cache_dir=str(cache_dir)) == []


def test_stale_deb_cache_missing_cache_dir_returns_empty(monkeypatch, tmp_path):
    responses = [(_starts_with("dpkg", "-l"), _completed(["dpkg"], stdout=DPKG_L_FOR_CACHE))]
    _install_fake_run(monkeypatch, responses)

    missing_dir = tmp_path / "does-not-exist"

    assert stale_deb_cache(cache_dir=str(missing_dir)) == []


# --- orphaned_config_files ---


def test_orphaned_config_files_parses_rc_status_packages(monkeypatch):
    responses = [
        (_starts_with("dpkg", "-l"), _completed(["dpkg"], stdout=DPKG_L_WITH_RC)),
        (
            _starts_with("dpkg-query", "-W"),
            _completed(
                ["dpkg-query"],
                stdout=_dpkg_query_output([("old-removed-package", 4), ("another-purged-thing", 0)]),
            ),
        ),
    ]
    _install_fake_run(monkeypatch, responses)

    findings = orphaned_config_files()

    names = {f["description"] for f in findings}
    assert len(findings) == 2
    assert any("old-removed-package" in d for d in names)
    assert any("another-purged-thing" in d for d in names)
    for f in findings:
        assert f["category"] == "orphaned_config_file"
        assert f["safe_to_auto_apply"] is True
    assert any(f["estimated_size_bytes"] == 4 * 1024 for f in findings)


def test_orphaned_config_files_ignores_installed_packages(monkeypatch):
    responses = [
        (_starts_with("dpkg", "-l"), _completed(["dpkg"], stdout=DPKG_L_WITH_RC)),
        (_starts_with("dpkg-query", "-W"), _completed(["dpkg-query"], stdout="")),
    ]
    _install_fake_run(monkeypatch, responses)

    findings = orphaned_config_files()

    assert all("adduser" not in f["description"] for f in findings)


# --- AptQueryError ---


def test_apt_query_error_raised_on_non_zero_exit(monkeypatch):
    responses = [
        (
            _starts_with("dpkg", "-l"),
            _completed(["dpkg", "-l"], stdout="", stderr="dpkg: permission denied", returncode=1),
        ),
    ]
    _install_fake_run(monkeypatch, responses)

    with pytest.raises(AptQueryError, match="dpkg"):
        orphaned_config_files()


def test_apt_query_error_raised_on_timeout(monkeypatch):
    def raise_timeout(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=30)

    monkeypatch.setattr("backend.app.apt_clutter.subprocess.run", raise_timeout)

    with pytest.raises(AptQueryError, match="timed out"):
        orphaned_config_files()


def test_apt_query_error_raised_when_binary_missing(monkeypatch):
    def raise_not_found(args, **kwargs):
        raise FileNotFoundError("no such file or directory: 'dpkg'")

    monkeypatch.setattr("backend.app.apt_clutter.subprocess.run", raise_not_found)

    with pytest.raises(AptQueryError, match="Failed to run"):
        orphaned_config_files()


def test_dpkg_query_partial_failure_is_not_treated_as_error(monkeypatch):
    # dpkg-query -W exits non-zero when one of several requested packages is
    # unknown, but still prints data for the ones it found on stdout - this
    # must not raise, since it's not a real failure.
    responses = [
        (_starts_with("dpkg", "-l"), _completed(["dpkg"], stdout=DPKG_L_WITH_RC)),
        (
            _starts_with("dpkg-query", "-W"),
            _completed(
                ["dpkg-query"],
                stdout=_dpkg_query_output([("old-removed-package", 4)]),
                stderr="dpkg-query: no packages found matching another-purged-thing",
                returncode=1,
            ),
        ),
    ]
    _install_fake_run(monkeypatch, responses)

    findings = orphaned_config_files()

    assert len(findings) == 2  # both rc packages still reported, just with size 0 for the missing one


# --- scan_apt_clutter ---


def test_scan_apt_clutter_combines_all_categories(monkeypatch, audit_calls):
    def fake_orphaned_packages():
        return [{"category": "orphaned_package", "description": "x", "estimated_size_bytes": 1, "safe_to_auto_apply": False, "target_paths": ["pkg-x"]}]

    def fake_old_kernels():
        return [{"category": "old_kernel", "description": "y", "estimated_size_bytes": 2, "safe_to_auto_apply": False, "target_paths": ["linux-image-y"]}]

    def fake_stale_deb_cache():
        return [{"category": "stale_deb_cache", "description": "z", "estimated_size_bytes": 3, "safe_to_auto_apply": True, "target_paths": ["/var/cache/apt/archives/z.deb"]}]

    def fake_orphaned_config_files():
        return [{"category": "orphaned_config_file", "description": "w", "estimated_size_bytes": 4, "safe_to_auto_apply": True, "target_paths": ["pkg-w"]}]

    monkeypatch.setattr("backend.app.apt_clutter.orphaned_packages", fake_orphaned_packages)
    monkeypatch.setattr("backend.app.apt_clutter.old_kernels", fake_old_kernels)
    monkeypatch.setattr("backend.app.apt_clutter.stale_deb_cache", fake_stale_deb_cache)
    monkeypatch.setattr("backend.app.apt_clutter.orphaned_config_files", fake_orphaned_config_files)

    findings = scan_apt_clutter()

    categories = {f["category"] for f in findings}
    assert len(findings) == 4
    assert categories == {
        "orphaned_package",
        "old_kernel",
        "stale_deb_cache",
        "orphaned_config_file",
    }

    # Every finding should have produced exactly one "recommend" audit entry,
    # keyed off that finding's own description/target_paths.
    assert len(audit_calls) == 4
    assert {call["action_type"] for call in audit_calls} == {"recommend"}
    logged_reasons = {call["reason"] for call in audit_calls}
    assert logged_reasons == {"x", "y", "z", "w"}
    logged_targets = [tuple(call["target_paths"]) for call in audit_calls]
    assert ("pkg-x",) in logged_targets
    assert ("linux-image-y",) in logged_targets
    assert ("/var/cache/apt/archives/z.deb",) in logged_targets
    assert ("pkg-w",) in logged_targets


def test_scan_apt_clutter_logs_nothing_when_no_findings(monkeypatch, audit_calls):
    monkeypatch.setattr("backend.app.apt_clutter.orphaned_packages", lambda: [])
    monkeypatch.setattr("backend.app.apt_clutter.old_kernels", lambda: [])
    monkeypatch.setattr("backend.app.apt_clutter.stale_deb_cache", lambda: [])
    monkeypatch.setattr("backend.app.apt_clutter.orphaned_config_files", lambda: [])

    findings = scan_apt_clutter()

    assert findings == []
    assert audit_calls == []


# --- apply_finding ---


def _finding(category, target_paths, safe, description="a finding"):
    return {
        "category": category,
        "description": description,
        "estimated_size_bytes": 100,
        "safe_to_auto_apply": safe,
        "target_paths": target_paths,
    }


@pytest.mark.parametrize("category", ["old_kernel", "orphaned_package"])
def test_apply_finding_rejects_unsafe_categories(category, audit_calls):
    finding = _finding(category, ["some-target"], safe=False)

    with pytest.raises(UnsafeApplyError, match="not marked safe_to_auto_apply"):
        apply_finding(finding)

    # A refusal must never touch the filesystem or the audit trail.
    assert audit_calls == []


def test_apply_finding_rejects_when_safe_flag_true_but_category_unrecognized(audit_calls):
    # Defense in depth: even if safe_to_auto_apply were True, only the two
    # categories with a real apply implementation may proceed.
    finding = _finding("orphaned_package", ["some-target"], safe=True)

    with pytest.raises(UnsafeApplyError, match="no safe apply action"):
        apply_finding(finding)

    assert audit_calls == []


def test_apply_finding_stale_deb_cache_deletes_real_file_and_logs(tmp_path, audit_calls):
    deb_file = tmp_path / "old-removed-package_1.2.3-1_amd64.deb"
    deb_file.write_bytes(b"0" * 2048)

    finding = _finding(
        "stale_deb_cache",
        [str(deb_file)],
        safe=True,
        description="Cached package file is stale and can be safely removed.",
    )

    result = apply_finding(finding)

    assert result == {"applied": True, "finding": finding}
    assert not deb_file.exists()

    assert len(audit_calls) == 1
    assert audit_calls[0]["action_type"] == "apt_clutter_apply"
    assert audit_calls[0]["target_paths"] == [str(deb_file)]
    assert audit_calls[0]["reason"] == finding["description"]


def test_apply_finding_stale_deb_cache_missing_file_raises_apt_query_error(tmp_path, audit_calls):
    deb_file = tmp_path / "already-gone_1.0-1_amd64.deb"  # never created

    finding = _finding("stale_deb_cache", [str(deb_file)], safe=True)

    with pytest.raises(AptQueryError, match="Failed to remove"):
        apply_finding(finding)

    assert audit_calls == []


def test_apply_finding_orphaned_config_file_purges_package(monkeypatch, audit_calls):
    responses = [
        (
            _starts_with("apt-get", "purge", "-y", "old-removed-package"),
            _completed(["apt-get"], stdout="Purging configuration files for old-removed-package"),
        ),
    ]
    fake = _install_fake_run(monkeypatch, responses)

    finding = _finding(
        "orphaned_config_file",
        ["old-removed-package"],
        safe=True,
        description="'old-removed-package' was removed but its configuration files remain.",
    )

    result = apply_finding(finding)

    assert result == {"applied": True, "finding": finding}
    assert fake.calls == [["apt-get", "purge", "-y", "old-removed-package"]]

    assert len(audit_calls) == 1
    assert audit_calls[0]["action_type"] == "apt_clutter_apply"
    assert audit_calls[0]["target_paths"] == ["old-removed-package"]
    assert audit_calls[0]["reason"] == finding["description"]


def test_apply_finding_orphaned_config_file_raises_on_purge_failure(monkeypatch, audit_calls):
    responses = [
        (
            _starts_with("apt-get", "purge", "-y", "old-removed-package"),
            _completed(
                ["apt-get"], stdout="", stderr="E: Unable to locate package", returncode=1
            ),
        ),
    ]
    _install_fake_run(monkeypatch, responses)

    finding = _finding("orphaned_config_file", ["old-removed-package"], safe=True)

    with pytest.raises(AptQueryError, match="apt-get"):
        apply_finding(finding)

    assert audit_calls == []
