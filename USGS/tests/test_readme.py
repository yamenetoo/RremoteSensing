"""The README examples must run, and its function catalogue must match the code."""
import re
from pathlib import Path

import matplotlib
import pytest

import usgs_splib07 as splib

README = (Path(__file__).resolve().parents[1] / "README.md").read_text()


def test_readme_example_blocks_run():
    matplotlib.use("Agg")
    blocks = re.findall(r"<!-- run -->\n```python\n(.*?)```", README, flags=re.S)
    assert len(blocks) >= 8
    ns = {}
    for code in blocks:
        exec(compile(code, "<README>", "exec"), ns)


def test_readme_catalogue_is_current():
    m = re.search(r"<!-- catalogue:start -->\n(.*?)<!-- catalogue:end -->", README, flags=re.S)
    assert m and m.group(1).rstrip() == splib.catalogue_markdown(compact=True).rstrip(), \
        "README catalogue is stale: regenerate it from splib.catalogue_markdown(compact=True)"


def test_readme_mentions_every_public_function():
    for name in splib.list_functions()["name"]:
        assert name.split(".")[-1] in README, name
