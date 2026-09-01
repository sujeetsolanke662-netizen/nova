from backend.app.dedup import compute_file_hash, find_exact_duplicates


def _meta(path, size_bytes):
    return {"path": str(path), "size_bytes": size_bytes}


def test_compute_file_hash_matches_for_identical_content(tmp_path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_bytes(b"same content" * 100)
    file_b.write_bytes(b"same content" * 100)

    assert compute_file_hash(str(file_a)) == compute_file_hash(str(file_b))


def test_compute_file_hash_streams_large_file_in_chunks(tmp_path):
    big_file = tmp_path / "big.bin"
    # Larger than the default chunk_size, and not an even multiple of it,
    # to exercise the final short read.
    big_file.write_bytes(b"x" * (65536 * 3 + 17))

    assert compute_file_hash(str(big_file), chunk_size=65536) == compute_file_hash(
        str(big_file), chunk_size=4096
    )


def test_find_exact_duplicates_groups_matching_content(tmp_path):
    dup1 = tmp_path / "dup1.txt"
    dup2 = tmp_path / "dup2.txt"
    unique = tmp_path / "unique.txt"
    dup1.write_text("duplicate content")
    dup2.write_text("duplicate content")
    unique.write_text("different content!")

    files = [
        _meta(dup1, dup1.stat().st_size),
        _meta(dup2, dup2.stat().st_size),
        _meta(unique, unique.stat().st_size),
    ]

    groups = find_exact_duplicates(files)

    assert len(groups) == 1
    group = groups[0]
    assert set(group["paths"]) == {str(dup1), str(dup2)}
    assert group["size_bytes"] == dup1.stat().st_size
    assert group["hash"] == compute_file_hash(str(dup1))


def test_find_exact_duplicates_skips_hashing_unique_sized_file(tmp_path, monkeypatch):
    dup1 = tmp_path / "dup1.txt"
    dup2 = tmp_path / "dup2.txt"
    unique = tmp_path / "unique.txt"
    dup1.write_text("aa")
    dup2.write_text("aa")
    unique.write_text("a much longer unique file body")

    files = [
        _meta(dup1, dup1.stat().st_size),
        _meta(dup2, dup2.stat().st_size),
        _meta(unique, unique.stat().st_size),
    ]

    hashed_paths = []
    import backend.app.dedup as dedup_module

    real_compute_file_hash = dedup_module.compute_file_hash

    def tracking_compute_file_hash(path, *args, **kwargs):
        hashed_paths.append(path)
        return real_compute_file_hash(path, *args, **kwargs)

    monkeypatch.setattr(dedup_module, "compute_file_hash", tracking_compute_file_hash)

    groups = dedup_module.find_exact_duplicates(files)

    assert len(groups) == 1
    assert set(groups[0]["paths"]) == {str(dup1), str(dup2)}
    # The uniquely-sized file must never have been hashed at all.
    assert str(unique) not in hashed_paths
    assert set(hashed_paths) == {str(dup1), str(dup2)}


def test_find_exact_duplicates_on_empty_input_returns_empty_list():
    assert find_exact_duplicates([]) == []


def test_find_exact_duplicates_no_groups_when_all_sizes_unique(tmp_path):
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("a")
    file_b.write_text("bb")

    files = [
        _meta(file_a, file_a.stat().st_size),
        _meta(file_b, file_b.stat().st_size),
    ]

    assert find_exact_duplicates(files) == []
