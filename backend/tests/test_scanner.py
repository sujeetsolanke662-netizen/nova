from pathlib import Path

import pytest

from backend.app.guardrails import load_protected_patterns
from backend.app.scanner import scan_directory

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "protected_paths.yaml"


@pytest.fixture(scope="module")
def patterns():
    return load_protected_patterns(str(CONFIG_PATH))


def test_scan_directory_finds_files_in_tree(tmp_path, patterns):
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    (scan_root / "a.txt").write_text("hello")
    subdir = scan_root / "subdir"
    subdir.mkdir()
    (subdir / "b.log").write_text("world")

    files, skipped = scan_directory(str(scan_root), [str(scan_root)], patterns)

    paths = {f["path"] for f in files}
    assert paths == {
        str((scan_root / "a.txt").resolve()),
        str((subdir / "b.log").resolve()),
    }
    assert skipped == []

    by_path = {f["path"]: f for f in files}
    a_entry = by_path[str((scan_root / "a.txt").resolve())]
    assert a_entry["size_bytes"] == len("hello")
    assert a_entry["extension"] == ".txt"
    assert "last_accessed" in a_entry
    assert "last_modified" in a_entry


def test_scan_directory_skips_protected_pattern(tmp_path, patterns):
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    (scan_root / "normal.txt").write_text("keep me")

    git_dir = scan_root / "repo" / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")

    files, _skipped = scan_directory(str(scan_root), [str(scan_root)], patterns)

    paths = {f["path"] for f in files}
    assert str((scan_root / "normal.txt").resolve()) in paths
    assert not any(".git" in p for p in paths)


def test_scan_directory_skips_paths_outside_scan_roots(tmp_path, patterns):
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    (scan_root / "inside.txt").write_text("in scope")

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "outside.txt").write_text("not in scope")

    # Walk a parent directory that contains both scan_root and outside_dir,
    # but only declare scan_root as an actual scan root - outside.txt must
    # be classified as out of scope and excluded even though scan_directory
    # physically walks past it.
    files, _skipped = scan_directory(str(tmp_path), [str(scan_root)], patterns)

    paths = {f["path"] for f in files}
    assert str((scan_root / "inside.txt").resolve()) in paths
    assert str((outside_dir / "outside.txt").resolve()) not in paths


def test_scan_directory_collects_unreadable_paths_as_skipped(tmp_path, patterns, monkeypatch):
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()
    bad_file = scan_root / "bad.txt"
    bad_file.write_text("data")

    real_stat = Path.stat

    def flaky_stat(self, *args, **kwargs):
        # pathlib's is_symlink()/lstat() are implemented in terms of
        # stat(follow_symlinks=False) internally, so only fail the "real"
        # stat() call scan_directory makes to collect metadata - not the
        # lstat-style calls made along the way to check for symlinks.
        if self.name == "bad.txt" and kwargs.get("follow_symlinks", True):
            raise PermissionError("permission denied")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)

    files, skipped = scan_directory(str(scan_root), [str(scan_root)], patterns)

    assert files == []
    assert len(skipped) == 1
    assert skipped[0]["path"] == str(bad_file.resolve())
    assert "permission denied" in skipped[0]["reason"]


def test_scan_directory_empty_tree_returns_empty_results(tmp_path, patterns):
    scan_root = tmp_path / "scan_root"
    scan_root.mkdir()

    files, skipped = scan_directory(str(scan_root), [str(scan_root)], patterns)

    assert files == []
    assert skipped == []
