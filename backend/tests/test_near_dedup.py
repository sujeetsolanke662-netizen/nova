from PIL import Image

from backend.app.near_dedup import (
    compute_image_phash,
    compute_minhash_signature,
    find_all_near_duplicates,
    find_near_duplicate_images,
    find_near_duplicate_text,
)


def _meta(path):
    return {"path": str(path), "size_bytes": path.stat().st_size}


def _solid_image(path, color, size=(64, 64)):
    Image.new("RGB", size, color=color).save(path)


def _gradient_image(path, size=(64, 64), horizontal=True):
    """A gradient has actual pixel structure (unlike a solid color, whose
    phash collapses to ~the same hash for any color), so it's useful for
    exercising phash's tolerance to small global changes vs its sensitivity
    to structural ones."""
    width, height = size
    img = Image.new("RGB", size)
    for x in range(width):
        for y in range(height):
            v = int(255 * ((x / width) if horizontal else (y / height)))
            img.putpixel((x, y), (v, 255 - v, (v * 2) % 255))
    img.save(path)


def test_find_near_duplicate_text_groups_near_identical_and_excludes_different(tmp_path):
    base = tmp_path / "original.py"
    near = tmp_path / "near_copy.py"
    different = tmp_path / "different.py"

    base_text = "\n".join(f"def function_{i}():\n    return {i}" for i in range(300))
    # A couple of names changed relative to base_text - still highly similar
    # since it's a small fraction of a much larger shared body.
    near_text = base_text.replace("function_3", "function_three").replace(
        "function_10", "function_ten"
    )
    different_text = "\n".join(f"class Widget{i}:\n    pass" for i in range(300))

    base.write_text(base_text)
    near.write_text(near_text)
    different.write_text(different_text)

    files = [_meta(base), _meta(near), _meta(different)]
    groups = find_near_duplicate_text(files, jaccard_threshold=0.8)

    assert len(groups) == 1
    group = groups[0]
    assert set(group["paths"]) == {str(base), str(near)}
    assert group["similarity_type"] == "text_near_duplicate"
    assert group["avg_similarity"] >= 0.8
    assert str(different) not in group["paths"]


def test_compute_minhash_signature_returns_none_for_binary_file(tmp_path):
    binary_file = tmp_path / "data.bin"
    binary_file.write_bytes(bytes(range(256)) * 4)

    assert compute_minhash_signature(str(binary_file)) is None


def test_find_near_duplicate_text_excludes_undecodable_binary_file(tmp_path):
    text_a = tmp_path / "a.txt"
    text_b = tmp_path / "b.txt"
    binary_file = tmp_path / "c.txt"

    base_text = "\n".join(f"Sentence number {i} in the document." for i in range(300))
    near_text = base_text.replace("number 3 ", "number three ").replace(
        "number 10 ", "number ten "
    )
    text_a.write_text(base_text)
    text_b.write_text(near_text)
    binary_file.write_bytes(bytes(range(256)) * 4)

    files = [_meta(text_a), _meta(text_b), _meta(binary_file)]
    groups = find_near_duplicate_text(files, jaccard_threshold=0.8)

    assert len(groups) == 1
    assert str(binary_file) not in groups[0]["paths"]


def test_compute_image_phash_returns_none_for_corrupt_file(tmp_path):
    fake_image = tmp_path / "fake.png"
    fake_image.write_bytes(b"not actually a png")

    assert compute_image_phash(str(fake_image)) is None


def test_find_near_duplicate_images_excludes_corrupt_file_without_crashing(tmp_path):
    real_a = tmp_path / "a.png"
    real_b = tmp_path / "b.png"
    corrupt = tmp_path / "corrupt.png"

    _solid_image(real_a, (200, 50, 50))
    _solid_image(real_b, (200, 50, 50))
    corrupt.write_bytes(b"not actually a png")

    files = [_meta(real_a), _meta(real_b), _meta(corrupt)]
    groups = find_near_duplicate_images(files)

    assert len(groups) == 1
    assert set(groups[0]["paths"]) == {str(real_a), str(real_b)}
    assert str(corrupt) not in groups[0]["paths"]


def test_find_near_duplicate_images_groups_pixel_identical_images(tmp_path):
    img_a = tmp_path / "square_a.png"
    img_b = tmp_path / "square_b.png"

    _solid_image(img_a, (10, 120, 200))
    _solid_image(img_b, (10, 120, 200))

    files = [_meta(img_a), _meta(img_b)]
    groups = find_near_duplicate_images(files, hamming_threshold=5)

    assert len(groups) == 1
    group = groups[0]
    assert group["similarity_type"] == "image_near_duplicate"
    assert set(group["paths"]) == {str(img_a), str(img_b)}
    assert group["avg_hamming_distance"] == 0.0


def test_find_near_duplicate_images_groups_slightly_altered_image(tmp_path):
    img_a = tmp_path / "gradient_a.png"
    img_b = tmp_path / "gradient_b.png"

    _gradient_image(img_a)
    # A small uniform brightness bump across the whole image - the kind of
    # change re-compression or a minor edit would introduce - leaves the
    # image's coarse structure, and so its phash, effectively unchanged.
    base = Image.open(img_a)
    Image.eval(base, lambda v: min(255, v + 3)).save(img_b)

    files = [_meta(img_a), _meta(img_b)]
    groups = find_near_duplicate_images(files, hamming_threshold=5)

    assert len(groups) == 1
    assert set(groups[0]["paths"]) == {str(img_a), str(img_b)}


def test_find_near_duplicate_images_no_group_for_dissimilar_images(tmp_path):
    img_a = tmp_path / "gradient_horizontal.png"
    img_b = tmp_path / "gradient_vertical.png"

    _gradient_image(img_a, horizontal=True)
    _gradient_image(img_b, horizontal=False)

    files = [_meta(img_a), _meta(img_b)]
    groups = find_near_duplicate_images(files, hamming_threshold=5)

    assert groups == []


def test_find_all_near_duplicates_merges_image_and_text_results(tmp_path):
    img_a = tmp_path / "square_a.png"
    img_b = tmp_path / "square_b.png"
    _solid_image(img_a, (10, 120, 200))
    _solid_image(img_b, (10, 120, 200))

    text_a = tmp_path / "a.md"
    text_b = tmp_path / "b.md"
    base_text = "\n".join(f"Sentence number {i} in the document." for i in range(300))
    near_text = base_text.replace("number 3 ", "number three ").replace(
        "number 10 ", "number ten "
    )
    text_a.write_text(base_text)
    text_b.write_text(near_text)

    files = [_meta(img_a), _meta(img_b), _meta(text_a), _meta(text_b)]
    groups = find_all_near_duplicates(files)

    similarity_types = {g["similarity_type"] for g in groups}
    assert similarity_types == {"image_near_duplicate", "text_near_duplicate"}
    assert len(groups) == 2

    image_group = next(g for g in groups if g["similarity_type"] == "image_near_duplicate")
    text_group = next(g for g in groups if g["similarity_type"] == "text_near_duplicate")
    assert set(image_group["paths"]) == {str(img_a), str(img_b)}
    assert set(text_group["paths"]) == {str(text_a), str(text_b)}
