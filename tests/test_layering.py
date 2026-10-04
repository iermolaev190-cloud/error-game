"""Тест слоёв: ``domain/`` не знает про инфраструктуру, фреймворки и интерфейсы.

Правило MASTER_SPEC §12 и 20_TECH_ARCHITECTURE_V1 §15. Тест обязателен: он
должен падать, если в domain появится любой из запрещённых импортов.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
DOMAIN_ROOT = SRC_ROOT / "world_error" / "domain"

FORBIDDEN_TOP_LEVEL = frozenset({"sqlalchemy", "alembic", "aiogram", "pydantic", "pydantic_settings"})
FORBIDDEN_BARE_LAYERS = frozenset({"infrastructure", "interfaces", "bootstrap"})
FORBIDDEN_WORLD_ERROR_PREFIXES = (
    "world_error.infrastructure",
    "world_error.interfaces",
    "world_error.bootstrap",
)

DOMAIN_MODULES = sorted(DOMAIN_ROOT.rglob("*.py"))


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(SRC_ROOT).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _package_parts(path: Path) -> list[str]:
    parts = _module_name(path).split(".")
    if path.name != "__init__.py":
        parts = parts[:-1]
    return parts


def _imported_modules(tree: ast.AST, path: Path) -> list[str]:
    package = _package_parts(path)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(package) - (node.level - 1)
                base = package[:keep] if keep > 0 else []
                module_parts = node.module.split(".") if node.module else []
                found.append(".".join([*base, *module_parts]))
            elif node.module:
                found.append(node.module)
    return found


def _is_forbidden(imported: str) -> bool:
    if not imported:
        return False
    top_level = imported.split(".")[0]
    if top_level in FORBIDDEN_TOP_LEVEL or top_level in FORBIDDEN_BARE_LAYERS:
        return True
    return any(
        imported == prefix or imported.startswith(f"{prefix}.")
        for prefix in FORBIDDEN_WORLD_ERROR_PREFIXES
    )


def test_domain_layer_is_not_empty() -> None:
    assert len(DOMAIN_MODULES) >= 6, (
        f"domain/ содержит всего {len(DOMAIN_MODULES)} модулей — тест слоёв ничего не проверяет"
    )


@pytest.mark.parametrize(
    "path",
    DOMAIN_MODULES,
    ids=[str(path.relative_to(REPO_ROOT)) for path in DOMAIN_MODULES],
)
def test_domain_does_not_import_forbidden_modules(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = sorted({name for name in _imported_modules(tree, path) if _is_forbidden(name)})
    assert not violations, f"{path.relative_to(REPO_ROOT)} импортирует запрещённое: {violations}"
