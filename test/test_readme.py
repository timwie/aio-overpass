from pathlib import Path


root_dir = Path(__file__).parent.parent
readme_path = root_dir / "README.md"


def test_usage_doc_in_readme():
    usage_doc_path = root_dir / "aio_overpass" / "doc" / "usage.md"
    assert usage_doc_path.read_text() in readme_path.read_text()


def test_extras_doc_in_readme():
    extras_doc_path = root_dir / "aio_overpass" / "doc" / "extras.md"
    assert extras_doc_path.read_text() in readme_path.read_text()
