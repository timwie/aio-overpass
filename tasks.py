from invoke import task, Context

@task
def doc(c: Context):
    """Generate documentation"""
    c.run("pdoc -o ./doc aio_overpass/", echo=True)

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
    c.run("isort aio_overpass/", echo=True)
    c.run("isort test/", echo=True)
    c.run("black aio_overpass/", echo=True)
    c.run("black test/", echo=True)

@task
def lint(c: Context):
    """Run linter"""
    c.run("ruff check aio_overpass/", echo=True)

@task
def test(c: Context):
    """Run tests"""
    c.run("pytest -vv --cov=aio_overpass/", echo=True)

@task
def test_publish(c: Context):
    """Perform a dry run of publishing the package"""
    c.run("poetry publish --build --dry-run", echo=True)

@task
def update(c: Context):
    """Update dependencies"""
    c.run("poetry self update", echo=True)
    c.run("poetry up --latest", echo=True)
    c.run("poetry show --outdated --why", echo=True)
