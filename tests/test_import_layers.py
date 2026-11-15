"""The packages of rasl import each other in one direction (pyproject.toml,
[tool.importlinter]). This runs those contracts with the rest of the tests."""

from __future__ import annotations

from importlinter.cli import lint_imports


def test_import_contracts_hold(capsys) -> None:
    exit_code = lint_imports()
    report = capsys.readouterr().out
    assert exit_code == 0, report
