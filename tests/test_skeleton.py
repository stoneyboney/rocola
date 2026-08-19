"""The fork's structural assertions.

Not busywork: each of these pins something that fails silently rather than
loudly, and two of them are mistakes Molcajete has already made once.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_shared_package_is_the_sibling_checkout() -> None:
    """molcajete-prep resolves to ../molcajete-prep, not to a copy in the venv.

    `tool.uv.sources` marks it editable by path so a fix upstream lands here
    without a reinstall. If this ever points inside `.venv/`, the two repos have
    started to drift and nobody will notice until the glosses differ.
    """
    import molcajete_prep

    resolved = Path(molcajete_prep.__file__).resolve()
    assert resolved == (ROOT.parent / "molcajete-prep/src/molcajete_prep/__init__.py")


def test_spacy_model_matches_molcajete() -> None:
    """The pinned Spanish model is 3.8.0, the same version Molcajete uses.

    A different model version means different lemmas, and therefore a different
    teach set for the same words. `tool.uv.sources` carries the wheel URL because
    the models are not on PyPI and the bare requirement cannot be satisfied —
    the single most likely thing to bite a third consumer.
    """
    import spacy

    assert spacy.load("es_core_news_sm").meta["version"] == "3.8.0"


def test_shared_pytest_guards_are_registered(request: pytest.FixtureRequest) -> None:
    """The guards ship from molcajete-prep's pytest plugin, not from conftest.

    `no_real_extracts` and `no_shared_cache` are autouse fixtures that stop a
    test streaming gigabytes of Wiktionary or writing the developer's real gloss
    cache. They arrive through the `pytest11` entry point. If the entry point
    stops being registered they vanish without any error, and the first symptom
    is a test suite that quietly downloads 22.9 GB.
    """
    names = request.session._fixturemanager._arg2fixturedefs
    assert "no_real_extracts" in names
    assert "no_shared_cache" in names


@pytest.mark.parametrize(
    "module",
    ["lastfm", "lrclib", "matcher", "langfilter", "variety"],
)
def test_prep_subpackages_import(module: str) -> None:
    """The five song-shaped packages exist and are importable while empty."""
    assert importlib.import_module(f"rocola_prep.{module}") is not None
