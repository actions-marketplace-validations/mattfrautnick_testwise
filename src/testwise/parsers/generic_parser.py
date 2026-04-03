"""Generic file-level parser. Fallback for languages without a dedicated parser."""

from __future__ import annotations

from pathlib import Path

from testwise.models import ParsedTest, ParsedTestFile, RunnerConfig
from testwise.parsers import BaseParser


class GenericParser(BaseParser):
    """File-level fallback parser.

    Treats each test file as a single test unit. No AST parsing.
    """

    name = "generic"
    languages = ["*"]
    file_patterns = ["*"]

    def parse_test_file(self, file_path: Path, content: str) -> ParsedTestFile:
        path_str = str(file_path)
        suffix = file_path.suffix.lstrip(".")
        language = _detect_language(suffix)

        return ParsedTestFile(
            file_path=path_str,
            language=language,
            tests=[
                ParsedTest(
                    name=file_path.name,
                    qualified_name=path_str,
                    file_path=path_str,
                    line_number=0,
                )
            ],
        )

    def build_run_command(
        self,
        tests: list[ParsedTest],
        runner_config: RunnerConfig,
        repo_root: Path,
    ) -> list[str]:
        cmd = [runner_config.command, *runner_config.args]

        file_paths = list({t.file_path for t in tests})

        if runner_config.file_arg_style == "append":
            cmd.extend(file_paths)
        elif runner_config.file_arg_style == "flag":
            pattern = "|".join(Path(p).stem for p in file_paths)
            cmd.extend([runner_config.file_arg_flag, pattern])

        return cmd


_LANGUAGE_MAP = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "jsx": "javascript",
    "go": "go",
    "rs": "rust",
    "java": "java",
    "rb": "ruby",
    "php": "php",
    "cs": "csharp",
    "cpp": "cpp",
    "c": "c",
    "swift": "swift",
    "kt": "kotlin",
    "scala": "scala",
    "ex": "elixir",
    "exs": "elixir",
}


def _detect_language(suffix: str) -> str:
    return _LANGUAGE_MAP.get(suffix, suffix or "unknown")
