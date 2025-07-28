from pathlib import Path

import pytest


root_dir = Path(__file__).parent.parent
readme_path = root_dir / "README.md"


@pytest.mark.xdist_group(name="fast")
def test_usage_doc_in_readme():
    usage_doc_path = root_dir / "aio_overpass" / "doc" / "usage.md"
    assert usage_doc_path.read_text(encoding="utf-8") in readme_path.read_text(encoding="utf-8")


@pytest.mark.xdist_group(name="fast")
def test_extras_doc_in_readme():
    extras_doc_path = root_dir / "aio_overpass" / "doc" / "extras.md"
    assert extras_doc_path.read_text(encoding="utf-8") in readme_path.read_text(encoding="utf-8")
