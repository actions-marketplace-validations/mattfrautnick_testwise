"""Python/pytest parser. Extracts test functions, classes, markers, and imports using AST."""

from __future__ import annotations

import ast
from pathlib import Path

from testwise.models import ParsedTest, ParsedTestFile, RunnerConfig
from testwise.parsers import BaseParser


class PytestParser(BaseParser):
    """AST-based pytest test parser.

    Extracts:
    - test_* functions and Test* class methods
    - @pytest.mark.* decorators (tags)
    - @pytest.mark.covers() custom annotations
    - @pytest.mark.parametrize detection
    - Import statements for dependency mapping
    - Fixture references from function parameters
    - Docstrings
    """

    name = "pytest"
    languages = ["python"]
    file_patterns = ["test_*.py", "*_test.py", "tests/**/*.py"]

    def parse_test_file(self, file_path: Path, content: str) -> ParsedTestFile:
        path_str = str(file_path)

        try:
            tree = ast.parse(content, filename=path_str)
        except SyntaxError:
            # Fall back to treating the file as a single test
            return ParsedTestFile(
                file_path=path_str,
                language="python",
                tests=[
                    ParsedTest(
                        name=file_path.name,
                        qualified_name=path_str,
                        file_path=path_str,
                    )
                ],
            )

        imports = _extract_imports(tree)
        tests: list[ParsedTest] = []
        fixtures_used: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                # Top-level test function
                test = _parse_test_function(node, path_str, class_name=None)
                tests.append(test)
                fixtures_used.update(_extract_fixtures(node))

            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                # Test class — extract methods
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                        test = _parse_test_function(item, path_str, class_name=node.name)
                        tests.append(test)
                        fixtures_used.update(_extract_fixtures(item))

        return ParsedTestFile(
            file_path=path_str,
            language="python",
            tests=tests,
            imports=imports,
            fixtures_used=sorted(fixtures_used),
        )

    def build_run_command(
        self,
        tests: list[ParsedTest],
        runner_config: RunnerConfig,
        repo_root: Path,
    ) -> list[str]:
        cmd = [runner_config.command, *runner_config.args]

        if len(tests) <= 10:
            # Use node IDs for precise selection
            for test in tests:
                cmd.append(test.qualified_name)
        else:
            # Use -k expression for many tests
            names = [t.name for t in tests]
            expr = " or ".join(names)
            cmd.extend(["-k", expr])

        return cmd


def _parse_test_function(
    node: ast.FunctionDef,
    file_path: str,
    class_name: str | None,
) -> ParsedTest:
    """Extract a ParsedTest from an AST function definition."""
    if class_name:
        qualified = f"{file_path}::{class_name}::{node.name}"
    else:
        qualified = f"{file_path}::{node.name}"

    tags = []
    covers = []
    parametrized = False

    for decorator in node.decorator_list:
        tag, cover_list, is_param = _parse_decorator(decorator)
        if tag:
            tags.append(tag)
        covers.extend(cover_list)
        if is_param:
            parametrized = True

    # Extract docstring
    description = ast.get_docstring(node)

    return ParsedTest(
        name=node.name,
        qualified_name=qualified,
        file_path=file_path,
        line_number=node.lineno,
        tags=tags,
        covers=covers,
        parametrized=parametrized,
        description=description,
    )


def _parse_decorator(node: ast.expr) -> tuple[str | None, list[str], bool]:
    """Parse a decorator and extract marker info.

    Returns: (tag_name, covers_list, is_parametrize)
    """
    # @pytest.mark.slow  ->  Attribute chain
    # @pytest.mark.covers("auth")  ->  Call with Attribute func
    # @pytest.mark.parametrize(...)  ->  Call with Attribute func

    attr_name = _get_marker_name(node)
    if attr_name is None:
        return None, [], False

    is_param = attr_name == "parametrize"

    # Check for covers() calls
    covers: list[str] = []
    if attr_name == "covers" and isinstance(node, ast.Call):
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                covers.append(arg.value)

    tag = attr_name if attr_name != "covers" else None

    return tag, covers, is_param


def _get_marker_name(node: ast.expr) -> str | None:
    """Extract the marker name from a pytest.mark.* decorator."""
    # Simple attribute: @pytest.mark.slow
    if isinstance(node, ast.Attribute):
        if _is_pytest_mark_chain(node):
            return node.attr
    # Call: @pytest.mark.parametrize(...)
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if _is_pytest_mark_chain(node.func):
            return node.func.attr
    return None


def _is_pytest_mark_chain(node: ast.Attribute) -> bool:
    """Check if an attribute node is pytest.mark.*."""
    # node.attr is the marker name, node.value should be pytest.mark
    if not isinstance(node.value, ast.Attribute):
        return False
    if node.value.attr != "mark":
        return False
    if isinstance(node.value.value, ast.Name) and node.value.value.id == "pytest":
        return True
    return False


def _extract_imports(tree: ast.Module) -> list[str]:
    """Extract import module names from an AST."""
    imports: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _extract_fixtures(node: ast.FunctionDef) -> list[str]:
    """Extract fixture names from function parameters (excluding 'self')."""
    fixtures = []
    for arg in node.args.args:
        if arg.arg not in ("self", "cls"):
            fixtures.append(arg.arg)
    return fixtures
