from invoke import task, Context

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
    c.run("isort aio_overpass/", echo=True, pty=True)
    c.run("isort test/", echo=True, pty=True)
    c.run("black aio_overpass/", echo=True, pty=True)
    c.run("black test/", echo=True, pty=True)

@task
def install(c: Context):
    """Install all dependencies"""
    c.run("poetry install --all-extras --with notebooks", echo=True, pty=True)

@task
def lint(c: Context):
    """Run linter and type checker"""
    c.run("ruff check aio_overpass/", echo=True, warn=True, pty=True)
    c.run("mypy aio_overpass/", echo=True, warn=True, pty=True)
    c.run("slotscheck -m aio_overpass", echo=True, warn=True, pty=True)
    c.run("pyright aio_overpass/", echo=True, warn=True, pty=True)

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
        c.run(f"papermill examples/pt_ordered.ipynb examples/pt_ordered_{name}.ipynb -p id {id} -p zoom {zoom} -p interactive False", echo=True)
        c.run("jupyter trust examples/*.ipynb", echo=True)

@task
def test(c: Context):
    """Run tests"""
    c.run("pytest -vv --cov=aio_overpass/", echo=True, pty=True)

@task
def test_publish(c: Context):
    """Perform a dry run of publishing the package"""
    c.run("poetry publish --build --dry-run --no-interaction", echo=True, pty=True)

@task
def tree(c: Context):
    """Display the tree of dependencies"""
    c.run("poetry show --without=dev,notebooks --tree", echo=True, pty=True)

@task
def update(c: Context):
    """Update dependencies"""
    c.run("poetry self update", echo=True, pty=True)
    c.run("poetry up --latest --only=dev,notebooks", echo=True, pty=True)
    c.run("poetry show --outdated --why", echo=True, pty=True)
