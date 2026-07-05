"""Nox sessions for Neutrino — linting, typing, testing."""

import nox

PYTHON_VERSIONS = ["3.11", "3.12"]


@nox.session(python=PYTHON_VERSIONS)
def test(session: nox.Session) -> None:
    """Run pytest with coverage on all supported Python versions."""
    session.install("-e", ".[test]")
    session.run("pytest", "tests/", *session.posargs)


@nox.session(python="3.12")
def lint(session: nox.Session) -> None:
    """Run ruff check and ruff format --check."""
    session.install("ruff>=0.5")
    session.run("ruff", "check", "src/", "tests/")
    session.run("ruff", "format", "--check", "src/", "tests/")


@nox.session(python="3.12")
def typecheck(session: nox.Session) -> None:
    """Run mypy in strict mode."""
    session.install("-e", ".[test]")
    session.run("mypy", "src/neutrino/")


@nox.session(python="3.12")
def format(session: nox.Session) -> None:
    """Auto-format code with ruff format."""
    session.install("ruff>=0.5")
    session.run("ruff", "format", "src/", "tests/")
    session.run("ruff", "check", "--fix", "src/", "tests/")


@nox.session(python="3.12")
def all_checks(session: nox.Session) -> None:
    """Run all checks: lint, typecheck, test."""
    session.install("-e", ".[dev,test]")
    session.run("ruff", "check", "src/", "tests/")
    session.run("ruff", "format", "--check", "src/", "tests/")
    session.run("mypy", "src/neutrino/")
    session.run("pytest", "tests/", *session.posargs)
