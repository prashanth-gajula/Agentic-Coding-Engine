# tools/file_tools.py

import os
from pathlib import Path
import subprocess
from typing import Optional

from langchain_core.tools import tool

# Root of the project the agents are allowed to touch.
# You can set PROJECT_ROOT in .env, otherwise cwd is used.
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path.cwd())).resolve()

PROJECT_ROOT = PROJECT_ROOT / 'Workflow_Testing'

def _resolve_safe(path: str) -> Path:
    """
    Resolve a path relative to PROJECT_ROOT and ensure we never escape the root.
    """
    full_path = (PROJECT_ROOT / path).resolve()
    if not str(full_path).startswith(str(PROJECT_ROOT)):
        raise ValueError(f"Access outside project root is not allowed: {full_path}")
    return full_path


@tool
def list_files(relative_dir: str = ".") -> str:
    """
    List files under the given directory (relative to project root).
    Returns a newline-separated list of paths.
    """
    try:
        base = _resolve_safe(relative_dir)
        if not base.exists():
            return f"ERROR: directory does not exist: {relative_dir}"

        paths = []
        # Limit number of files to avoid giant responses
        max_files = 300
        for root, _, files in os.walk(str(base)):
            for name in files:
                rel = Path(root, name).relative_to(PROJECT_ROOT)
                paths.append(str(rel))
                if len(paths) >= max_files:
                    break
            if len(paths) >= max_files:
                break

        if not paths:
            return f"No files found under: {relative_dir}"

        return "\n".join(paths)
    except Exception as e:
        return f"ERROR in list_files: {e}"


@tool
def read_file(path: str, max_chars: int = 8000) -> str:
    """
    Read a text file (relative to project root) and return its content.
    If the file is large, the content is truncated to max_chars characters.
    """
    try:
        full_path = _resolve_safe(path)
        if not full_path.exists():
            return f"ERROR: file does not exist: {path}"

        content = full_path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            return content[:max_chars] + f"\n\n...[TRUNCATED, {len(content) - max_chars} more chars]..."
        return content
    except Exception as e:
        return f"ERROR in read_file: {e}"


@tool
def write_file(path: str, content: str, create_dirs: bool = True) -> str:
    """
    Overwrite a text file (relative to project root) with the given content.
    If create_dirs is True, missing parent directories are created.
    """
    try:
        full_path = _resolve_safe(path)
        if create_dirs:
            full_path.parent.mkdir(parents=True, exist_ok=True)

        full_path.write_text(content, encoding="utf-8")
        return f"File written: {path}"
    except Exception as e:
        return f"ERROR in write_file: {e}"


@tool
def append_file(path: str, content: str, create_dirs: bool = True) -> str:
    """
    Append text to a file (relative to project root).
    Creates the file (and parent dirs) if it does not exist.
    """
    try:
        full_path = _resolve_safe(path)
        if create_dirs:
            full_path.parent.mkdir(parents=True, exist_ok=True)

        with full_path.open("a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended to file: {path}"
    except Exception as e:
        return f"ERROR in append_file: {e}"


@tool
def search_text(query: str, file_glob: str = "*.py", max_results: int = 50) -> str:
    """
    Search for a text query across project files matching file_glob (e.g. '*.py', '*.ts').
    Returns up to max_results matches with file path and line numbers.
    """
    try:
        matches = []
        for root, _, files in os.walk(str(PROJECT_ROOT)):
            for name in files:
                if not Path(name).match(file_glob):
                    continue
                full_path = Path(root, name)
                rel_path = full_path.relative_to(PROJECT_ROOT)

                try:
                    with full_path.open("r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, start=1):
                            if query in line:
                                matches.append(f"{rel_path}:{i}: {line.strip()}")
                                if len(matches) >= max_results:
                                    break
                except Exception:
                    # Ignore unreadable files
                    continue

            if len(matches) >= max_results:
                break

        if not matches:
            return f"No matches found for '{query}' in files matching '{file_glob}'."

        return "\n".join(matches)
    except Exception as e:
        return f"ERROR in search_text: {e}"


@tool
def apply_patch(
    path: str,
    original_snippet: str,
    new_snippet: str,
    occurrence: int = 1,
) -> str:
    """
    Safely update a file by replacing a specific occurrence of original_snippet
    with new_snippet.

    - path: relative file path.
    - original_snippet: exact text to look for.
    - new_snippet: replacement text.
    - occurrence: which occurrence to replace (1 = first, 2 = second, etc.).

    This is safer than rewriting the whole file and easier for the model
    than working with full unified diff syntax.
    """
    try:
        full_path = _resolve_safe(path)
        if not full_path.exists():
            return f"ERROR: file does not exist: {path}"

        content = full_path.read_text(encoding="utf-8")

        idx = -1
        start = 0
        for _ in range(occurrence):
            idx = content.find(original_snippet, start)
            if idx == -1:
                return (
                    f"ERROR: original_snippet not found (occurrence {occurrence}) "
                    f"in file: {path}"
                )
            start = idx + len(original_snippet)

        new_content = content[:idx] + new_snippet + content[idx + len(original_snippet):]
        full_path.write_text(new_content, encoding="utf-8")

        return (
            f"Patch applied to {path} (replaced occurrence {occurrence} of "
            f"original_snippet)."
        )
    except Exception as e:
        return f"ERROR in apply_patch: {e}"


@tool
def run_command(cmd: str, cwd: Optional[str] = None, timeout: int = 120) -> str:
    """
    Run a shell command (e.g. tests or build commands) inside the project.

    - cmd: command string, e.g. 'pytest', 'npm test', 'python -m pytest'.
    - cwd: optional working directory relative to project root.
    - timeout: max seconds before killing the process.

    Returns combined stdout and stderr (truncated if too long).
    """
    try:
        workdir = PROJECT_ROOT if cwd is None else _resolve_safe(cwd)

        completed = subprocess.run(
            cmd,
            shell=True,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        output = (
            f"Exit code: {completed.returncode}\n"
            f"--- STDOUT ---\n{completed.stdout}\n"
            f"--- STDERR ---\n{completed.stderr}"
        )

        max_chars = 8000
        if len(output) > max_chars:
            return output[:max_chars] + f"\n\n...[TRUNCATED, {len(output) - max_chars} more chars]..."

        return output
    except subprocess.TimeoutExpired:
        return f"ERROR: command timed out after {timeout} seconds: {cmd}"
    except Exception as e:
        return f"ERROR in run_command: {e}"
