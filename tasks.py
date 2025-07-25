import os

from invoke import task, Context


IS_CI = os.getenv("GITHUB_ACTIONS") == "true"


@task
def compile(c: Context):
    """Syntax-check/generate byte-code for all source files."""
    c.run('find aio_overpass/ -name "*.py" -exec python -m py_compile {} \\;', echo=True, pty=True)


@task
def doc(c: Context):
    """Generate documentation"""
    c.run("pdoc -o ./doc aio_overpass/", echo=True, pty=True)


@task
def doco(c: Context):
    """Generate documentation and open in browser"""
    from pathlib import Path
    import webbrowser

    doc(c)

    path = Path(__file__).parent / "doc" / "index.html"
    url = f"file://{path}"
    webbrowser.open(url, new=0, autoraise=True)


@task
def fmt(c: Context):
    """Run code formatters"""
    c.run("isort aio_overpass test", echo=True, pty=True)
    c.run("ruff format aio_overpass test tasks.py", echo=True, pty=True)


@task
def install(c: Context):
    """Install all dependencies"""
    c.run("uv lock", echo=True, pty=True)
    c.run("uv sync --all-extras --all-groups", echo=True, pty=True)


@task
def lint(c: Context):
    """Run linter and type checker"""
    c.run("ruff check aio_overpass/ test/", echo=True, warn=True, pty=True)
    c.run("slotscheck -m aio_overpass --require-subclass", echo=True, warn=True, pty=True)
    c.run("mypy aio_overpass/", echo=True, warn=True, pty=True)


@task
def papermill(c: Context):
    """Generate example notebooks with papermill"""

    files = [
        dict(
            name="hamburg_u3",
            id=1643221,
            zoom=13,
        )
    ]

    for file in files:
        name, id, zoom = file["name"], file["id"], file["zoom"]
        c.run(
            f"papermill examples/pt_ordered.ipynb examples/pt_ordered_{name}.ipynb -p id {id} -p zoom {zoom} -p interactive False",
            echo=True,
        )
        c.run("jupyter trust examples/*.ipynb", echo=True)


@task
def test(c: Context):
    """Run all tests in parallel"""
    _pytest(c, cov=not IS_CI, quick=False)  # show cov results when running local


@task
def test_cov(c: Context):
    """Run all tests in parallel, with coverage report"""
    _pytest(c, cov=True, quick=False)


@task
def test_quick(c: Context):
    """Run tests without the long-running ones"""
    _pytest(c, cov=not IS_CI, quick=True)  # show cov results when running local


def _pytest(c: Context, *, cov: bool, quick: bool):
    cmd = ["uv", "run", "pytest", "-vv"]

    if cov:
        cmd.append("--cov=aio_overpass/")

    if cov and IS_CI:
        cmd.append("--cov-report=xml")

    if quick:
        cmd.append("--ignore=test/test_large_data.py")
    else:
        cmd.append("--numprocesses=logical")
        cmd.append("--dist=loadgroup")

    c.run(" ".join(cmd), echo=True, pty=True)

    if cov and not IS_CI:
        c.run("rm .coverage*", echo=True, pty=True)


@task
def tree(c: Context):
    """Display the tree of dependencies"""
    c.run("uv tree --no-dev", echo=True, pty=True)


@task
def update(c: Context):
    """Update dependencies"""
    c.run("uv self update", echo=True, pty=True)
    c.run("uv lock --upgrade", echo=True, pty=True)
    install(c)
    c.run("uv pip list --outdated", echo=True, pty=True)
