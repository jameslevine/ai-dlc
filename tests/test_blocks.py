"""Tests for managed blocks.

The never-clobber promise lives or dies here, so these tests are about refusal
as much as about writing.
"""

from __future__ import annotations

from aidlc.render import blocks
from aidlc.render.blocks import Outcome


def make(content: str = "hello") -> str:
    return blocks.render("core", "1.0.0", content) + "\n"


def test_render_round_trips() -> None:
    text = make("body text")
    found = blocks.find(text, "core")

    assert found is not None
    assert found.content == "body text"
    assert found.version == "1.0.0"


def test_find_ignores_a_different_identifier() -> None:
    assert blocks.find(make(), "other") is None


def test_unterminated_block_is_not_treated_as_a_block() -> None:
    """A truncated file must not be appended to.

    If an unclosed marker read as "no block", upsert would add a second one and
    leave the file worse than it found it.
    """
    text = "<!-- aidlc:begin id=core version=1.0.0 digest=sha256:abc -->\nbody\n"
    assert blocks.find(text, "core") is None


def test_sync_will_not_create_a_block_in_an_unmarked_file() -> None:
    """Only init may add a block.

    Otherwise a stray `sync` in the wrong directory silently annotates
    unrelated documents.
    """
    result = blocks.upsert("Existing README.\n", "core", "1.0.0", "new")

    assert result.outcome is Outcome.ABSENT
    assert result.text == "Existing README.\n"


def test_init_appends_a_block_and_keeps_existing_content() -> None:
    result = blocks.upsert("My notes.\n", "core", "1.0.0", "generated", allow_create=True)

    assert result.outcome is Outcome.CREATED
    assert result.text.startswith("My notes.")
    assert "generated" in result.text


def test_identical_content_is_unchanged() -> None:
    result = blocks.upsert(make("same"), "core", "1.0.0", "same")
    assert result.outcome is Outcome.UNCHANGED


def test_new_content_updates_in_place_without_disturbing_the_rest() -> None:
    text = "Before.\n\n" + make("old") + "\nAfter.\n"
    result = blocks.upsert(text, "core", "1.0.0", "new")

    assert result.outcome is Outcome.UPDATED
    assert "new" in result.text
    assert "old" not in result.text
    assert result.text.startswith("Before.")
    assert result.text.rstrip().endswith("After.")


def test_hand_edited_block_is_refused() -> None:
    text = make("original").replace("original", "somebody edited this")
    result = blocks.upsert(text, "core", "1.0.0", "regenerated")

    assert result.outcome is Outcome.CONFLICT
    assert "edited by hand" in result.detail
    assert result.text == text, "a refusal must not modify the file"


def test_force_overrides_the_refusal() -> None:
    text = make("original").replace("original", "somebody edited this")
    result = blocks.upsert(text, "core", "1.0.0", "regenerated", force=True)

    assert result.outcome is Outcome.UPDATED
    assert "regenerated" in result.text


def test_digest_ignores_trailing_whitespace_and_line_endings() -> None:
    """Checkout differences must not read as a hand edit.

    Without this, a repository cloned with different autocrlf settings would
    report a conflict on every file the first time anyone ran sync.
    """
    assert blocks.content_digest("a\nb") == blocks.content_digest("a  \r\nb\n")
