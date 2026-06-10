"""Controlled tools for inspecting and fixing the Python environment.

Safety constraints:
    * Package installation uses ``sys.executable -m pip`` (never a bare ``pip``).
    * No arbitrary shell commands are executed; argument lists are fixed.
    * Subprocess calls capture stdout/stderr/return code and use a timeout.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from compufix_agents.config import PROJECT_ROOT
from compufix_agents.logging_config import get_logger
from compufix_agents.tools.runtime import get_runtime_preferences

logger = get_logger(__name__)

# Default timeout (seconds) for subprocess calls.
_DEFAULT_TIMEOUT = 120
# Creating a virtual environment can take a little longer than a plain install.
_VENV_CREATE_TIMEOUT = 120

# Maps an *import* name to the *pip package* name when they differ.
IMPORT_TO_PACKAGE: dict[str, str] = {
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
    "bs4": "beautifulsoup4",
    "skimage": "scikit-image",
    "Crypto": "pycryptodome",
    "OpenSSL": "pyOpenSSL",
    "psycopg2": "psycopg2-binary",
    "fitz": "PyMuPDF",
    "win32api": "pywin32",
    "serial": "pyserial",
}


def map_import_to_package(module_name: str) -> str:
    """Return the pip package name for a given import name.

    Falls back to the module name itself when no special mapping is known.

    Args:
        module_name: The import name, e.g. ``"cv2"``.

    Returns:
        The pip package name, e.g. ``"opencv-python"``.
    """
    return IMPORT_TO_PACKAGE.get(module_name, module_name)


def check_python_package(package_name: str) -> dict:
    """Check whether a package/module is importable in the current interpreter.

    This is a **read-only**, safe operation and does not require approval.

    Args:
        package_name: The import name (or pip package name) to check.

    Returns:
        A dict with keys: ``package_name``, ``installed`` (bool), and
        ``interpreter`` (path to the active Python).
    """
    # Check both the given name and its mapped/unmapped counterpart so that a
    # pip package name like "opencv-python" also resolves via its import "cv2".
    candidates = {package_name}
    for imp, pkg in IMPORT_TO_PACKAGE.items():
        if package_name in (imp, pkg):
            candidates.update({imp, pkg})

    installed = any(
        importlib.util.find_spec(name) is not None
        for name in candidates
        # find_spec only works on valid import names (no hyphens).
        if name.isidentifier()
    )
    logger.info("check_python_package(%s) -> installed=%s", package_name, installed)
    return {
        "package_name": package_name,
        "installed": installed,
        "interpreter": sys.executable,
    }


def _resolve_venv_dir(venv_path: str) -> Path:
    """Resolve a venv path relative to the project root (absolute paths kept)."""
    path = Path(venv_path).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path)


def _venv_python(venv_dir: Path) -> Path:
    """Return the path to the venv's Python interpreter for this OS."""
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def ensure_virtualenv(venv_path: str) -> dict:
    """Ensure a virtual environment exists, creating it if necessary.

    Args:
        venv_path: Target venv directory (relative to project root or absolute).

    Returns:
        A dict with ``success``, ``venv_dir``, ``python`` (interpreter path),
        ``created`` (bool), and ``message``.
    """
    venv_dir = _resolve_venv_dir(venv_path)
    py = _venv_python(venv_dir)

    if py.exists():
        return {
            "success": True,
            "venv_dir": str(venv_dir),
            "python": str(py),
            "created": False,
            "message": f"Using existing virtual environment at {venv_dir}.",
        }

    logger.info("Creating virtual environment at %s", venv_dir)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True,
            text=True,
            timeout=_VENV_CREATE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "venv_dir": str(venv_dir),
            "python": str(py),
            "created": False,
            "message": f"Virtual environment creation timed out after {_VENV_CREATE_TIMEOUT}s.",
        }
    except Exception as exc:  # pragma: no cover - unexpected OS-level failure.
        logger.exception("Failed to create virtual environment at %s", venv_dir)
        return {
            "success": False,
            "venv_dir": str(venv_dir),
            "python": str(py),
            "created": False,
            "message": f"Failed to create virtual environment: {exc}",
        }

    if proc.returncode != 0 or not py.exists():
        return {
            "success": False,
            "venv_dir": str(venv_dir),
            "python": str(py),
            "created": False,
            "message": f"Could not create virtual environment: {proc.stderr.strip()}",
        }

    return {
        "success": True,
        "venv_dir": str(venv_dir),
        "python": str(py),
        "created": True,
        "message": f"Created virtual environment at {venv_dir}.",
    }


def install_python_package(
    package_name: str,
    timeout: int = _DEFAULT_TIMEOUT,
    target: str | None = None,
) -> dict:
    """Install a package, honoring the user's runtime install preference.

    This is a **sensitive** operation that mutates the environment and must only
    be invoked after explicit user approval. The install *target* is decided by
    the runtime preference (or the ``target`` override):

        * ``"current"`` -> ``sys.executable -m pip install`` (current interpreter)
        * ``"venv"``    -> install into a project virtual environment, creating
          it first if it does not exist
        * ``"off"``     -> do not install; return guidance instead (security)

    Args:
        package_name: The pip package name to install.
        timeout: Maximum seconds to wait for pip to finish.
        target: Optional override for the install mode (``current`` / ``venv`` /
            ``off``). When ``None``, the runtime preference is used.

    Returns:
        A dict with ``package_name``, ``success``, ``returncode``, ``stdout``,
        ``stderr``, and ``interpreter`` (the Python used, when applicable).
    """
    prefs = get_runtime_preferences()
    mode = target or prefs.package_install_mode

    # Security choice: do not install anything.
    if mode == "off":
        manual = f"{sys.executable} -m pip install {package_name}"
        logger.info("install_python_package(%s) skipped (mode=off)", package_name)
        return {
            "package_name": package_name,
            "success": True,
            "skipped": True,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "interpreter": None,
            "message": (
                "Installation skipped per your security preference. "
                f"To install it yourself, run: {manual}"
            ),
        }

    # Decide which interpreter to install into.
    interpreter = sys.executable
    venv_info: dict | None = None
    if mode == "venv":
        venv_info = ensure_virtualenv(prefs.venv_path)
        if not venv_info["success"]:
            return {
                "package_name": package_name,
                "success": False,
                "returncode": None,
                "stdout": "",
                "stderr": venv_info["message"],
                "interpreter": venv_info["python"],
            }
        interpreter = venv_info["python"]

    cmd = [interpreter, "-m", "pip", "install", package_name]
    logger.info("install_python_package -> running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("install_python_package(%s) timed out", package_name)
        return {
            "package_name": package_name,
            "success": False,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": f"Installation timed out after {timeout}s.",
            "interpreter": interpreter,
        }
    except Exception as exc:  # pragma: no cover - unexpected OS-level failure.
        logger.exception("install_python_package(%s) failed", package_name)
        return {
            "package_name": package_name,
            "success": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "interpreter": interpreter,
        }

    success = proc.returncode == 0
    logger.info("install_python_package(%s) -> success=%s (mode=%s)", package_name, success, mode)
    result = {
        "package_name": package_name,
        "success": success,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "interpreter": interpreter,
    }
    if venv_info is not None:
        result["venv"] = venv_info
        if venv_info.get("created"):
            result["message"] = (
                f"Created virtual environment at {venv_info['venv_dir']} and installed "
                f"'{package_name}' into it."
            )
    return result


def verify_python_import(module_name: str, timeout: int = 30) -> dict:
    """Verify a module can be imported in a fresh subprocess.

    Running the import in a subprocess avoids polluting / caching state in the
    current process and reflects what a new ``python`` invocation would see.
    This is a **read-only**, safe operation.

    When the user's install preference targets a virtual environment, the import
    is verified against *that* environment's interpreter (so it reflects where
    the package was actually installed).

    Args:
        module_name: The import name to verify, e.g. ``"cv2"``.
        timeout: Maximum seconds to wait.

    Returns:
        A dict with ``module_name``, ``importable``, ``error`` (if any), and the
        ``interpreter`` used.
    """
    prefs = get_runtime_preferences()
    interpreter = sys.executable
    if prefs.package_install_mode == "venv":
        venv_py = _venv_python(_resolve_venv_dir(prefs.venv_path))
        if venv_py.exists():
            interpreter = str(venv_py)

    cmd = [interpreter, "-c", f"import {module_name}"]
    logger.info("verify_python_import -> %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "module_name": module_name,
            "importable": False,
            "error": f"Import check timed out after {timeout}s.",
            "interpreter": interpreter,
        }

    importable = proc.returncode == 0
    return {
        "module_name": module_name,
        "importable": importable,
        "error": "" if importable else proc.stderr.strip(),
        "interpreter": interpreter,
    }
