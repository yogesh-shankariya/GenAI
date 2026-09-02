#!/usr/bin/env python3
"""
repo_to_markdown.py

Create one Markdown file containing the contents of a repository folder.

Behavior:
- Recursively scans the input repo folder.
- Writes each included file with its relative path.
- Wraps text/code files in proper Markdown code fences.
- Does not dump CSV/Excel content; adds a placeholder instead.
- Skips common noisy folders like .git, __pycache__, venv, node_modules, etc.

Usage:
    python repo_to_markdown.py /path/to/repo
    python repo_to_markdown.py /path/to/repo -o repo_snapshot.md
"""

from __future__ import annotations

import argparse
import mimetypes
import os
from pathlib import Path
from typing import Iterable


PLACEHOLDER_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".xls",
    ".xlsx",
    ".xlsm",
    ".xlsb",
    ".ods",
}

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".idea",
    ".vscode",
}

DEFAULT_EXCLUDED_FILES = {
    ".DS_Store",
}

BINARY_PLACEHOLDER_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".pkl",
    ".joblib",
    ".parquet",
    ".feather",
    ".sqlite",
    ".db",
}

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".ipynb": "json",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".ps1": "powershell",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".md": "markdown",
    ".rst": "rst",
    ".txt": "text",
    ".dockerfile": "dockerfile",
}


def normalize_relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def is_hidden_path(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    return any(part.startswith(".") for part in relative_parts)


def should_skip_dir(path: Path, root: Path, include_hidden: bool) -> bool:
    if path.name in DEFAULT_EXCLUDED_DIRS:
        return True
    if not include_hidden and is_hidden_path(path, root):
        return True
    return False


def should_skip_file(path: Path, root: Path, output_path: Path, include_hidden: bool) -> bool:
    if path.name in DEFAULT_EXCLUDED_FILES:
        return True
    if path.resolve() == output_path.resolve():
        return True
    if not include_hidden and is_hidden_path(path, root):
        return True
    return False


def iter_repo_files(root: Path, output_path: Path, include_hidden: bool) -> Iterable[Path]:
    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)

        dir_names[:] = sorted(
            dirname
            for dirname in dir_names
            if not should_skip_dir(current_path / dirname, root, include_hidden)
        )

        for file_name in sorted(file_names):
            file_path = current_path / file_name
            if should_skip_file(file_path, root, output_path, include_hidden):
                continue
            yield file_path


def guess_markdown_language(path: Path) -> str:
    if path.name.lower() == "dockerfile":
        return "dockerfile"
    return LANGUAGE_BY_EXTENSION.get(path.suffix.lower(), "")


def is_probably_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_PLACEHOLDER_EXTENSIONS:
        return True

    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type and not (
        mime_type.startswith("text/")
        or mime_type in {
            "application/json",
            "application/xml",
            "application/x-yaml",
            "application/javascript",
        }
    ):
        return True

    try:
        with path.open("rb") as file:
            chunk = file.read(4096)
        return b"\x00" in chunk
    except OSError:
        return True


def read_text_file(path: Path) -> str:
    encodings = ("utf-8", "utf-8-sig", "latin-1")

    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue

    return path.read_text(encoding="utf-8", errors="replace")


def fence_content(content: str, language: str) -> str:
    fence = "```"

    if "```" in content:
        fence = "````"

    return f"{fence}{language}\n{content.rstrip()}\n{fence}\n"


def build_file_section(
    file_path: Path,
    root: Path,
    max_file_size_mb: float,
) -> str:
    relative_path = normalize_relative_path(file_path, root)
    extension = file_path.suffix.lower()

    lines: list[str] = [
        f"## `{relative_path}`",
        "",
    ]

    if extension in PLACEHOLDER_EXTENSIONS:
        lines.extend(
            [
                "> Placeholder: CSV/Excel-style file detected. Content was not included.",
                f"> File name: `{file_path.name}`",
                f"> Size: {file_path.stat().st_size:,} bytes",
                "",
            ]
        )
        return "\n".join(lines)

    file_size = file_path.stat().st_size
    max_bytes = int(max_file_size_mb * 1024 * 1024)

    if file_size > max_bytes:
        lines.extend(
            [
                f"> Placeholder: File is larger than {max_file_size_mb:g} MB, so content was not included.",
                f"> Size: {file_size:,} bytes",
                "",
            ]
        )
        return "\n".join(lines)

    if is_probably_binary(file_path):
        lines.extend(
            [
                "> Placeholder: Binary or non-text file detected. Content was not included.",
                f"> File name: `{file_path.name}`",
                f"> Size: {file_size:,} bytes",
                "",
            ]
        )
        return "\n".join(lines)

    content = read_text_file(file_path)
    language = guess_markdown_language(file_path)
    lines.append(fence_content(content, language))
    return "\n".join(lines)


def create_repo_markdown(
    repo_dir: Path,
    output_file: Path,
    include_hidden: bool = False,
    max_file_size_mb: float = 2.0,
) -> dict[str, int]:
    repo_dir = repo_dir.expanduser().resolve()
    output_file = output_file.expanduser().resolve()

    if not repo_dir.exists():
        raise FileNotFoundError(f"Repo folder does not exist: {repo_dir}")

    if not repo_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a folder: {repo_dir}")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    total_files = 0
    placeholder_files = 0
    included_text_files = 0

    with output_file.open("w", encoding="utf-8", newline="\n") as out:
        out.write(f"# Repository Snapshot\n\n")
        out.write(f"Root folder: `{repo_dir}`\n\n")
        out.write("---\n\n")

        for file_path in iter_repo_files(repo_dir, output_file, include_hidden):
            total_files += 1
            extension = file_path.suffix.lower()

            if (
                extension in PLACEHOLDER_EXTENSIONS
                or extension in BINARY_PLACEHOLDER_EXTENSIONS
                or file_path.stat().st_size > int(max_file_size_mb * 1024 * 1024)
                or is_probably_binary(file_path)
            ):
                placeholder_files += 1
            else:
                included_text_files += 1

            out.write(build_file_section(file_path, repo_dir, max_file_size_mb))
            out.write("\n---\n\n")

    return {
        "total_files_processed": total_files,
        "text_files_included": included_text_files,
        "placeholder_files": placeholder_files,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create one Markdown file containing repo files with paths."
    )
    parser.add_argument(
        "repo_dir",
        type=Path,
        help="Path to the repository folder.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("repo_snapshot.md"),
        help="Output Markdown file path. Default: repo_snapshot.md",
    )
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden files and folders. By default, hidden paths are skipped.",
    )
    parser.add_argument(
        "--max-file-size-mb",
        type=float,
        default=2.0,
        help="Maximum text file size to include. Larger files become placeholders. Default: 2 MB",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    stats = create_repo_markdown(
        repo_dir=args.repo_dir,
        output_file=args.output,
        include_hidden=args.include_hidden,
        max_file_size_mb=args.max_file_size_mb,
    )

    print(f"Markdown file created: {args.output.resolve()}")
    print(f"Total files processed: {stats['total_files_processed']}")
    print(f"Text files included: {stats['text_files_included']}")
    print(f"Placeholder files: {stats['placeholder_files']}")


if __name__ == "__main__":
    main()
