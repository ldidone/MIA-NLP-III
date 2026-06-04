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

from compufix_agents.logging_config import get_logger

logger = get_logger(__name__)

# Default timeout (seconds) for subprocess calls.
_DEFAULT_TIMEOUT = 120

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


def install_python_package(package_name: str, timeout: int = _DEFAULT_TIMEOUT) -> dict:
    """Install a package using ``sys.executable -m pip install``.

    This is a **sensitive** operation that mutates the environment and must only
    be invoked after explicit user approval.

    Args:
        package_name: The pip package name to install.
        timeout: Maximum seconds to wait for pip to finish.

    Returns:
        A dict with ``package_name``, ``success``, ``returncode``, ``stdout``,
        and ``stderr``.
    """
    cmd = [sys.executable, "-m", "pip", "install", package_name]
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
        }
    except Exception as exc:  # pragma: no cover - unexpected OS-level failure.
        logger.exception("install_python_package(%s) failed", package_name)
        return {
            "package_name": package_name,
            "success": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }

    success = proc.returncode == 0
    logger.info("install_python_package(%s) -> success=%s", package_name, success)
    return {
        "package_name": package_name,
        "success": success,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def verify_python_import(module_name: str, timeout: int = 30) -> dict:
    """Verify a module can be imported in a fresh subprocess.

    Running the import in a subprocess avoids polluting / caching state in the
    current process and reflects what a new ``python`` invocation would see.
    This is a **read-only**, safe operation.

    Args:
        module_name: The import name to verify, e.g. ``"cv2"``.
        timeout: Maximum seconds to wait.

    Returns:
        A dict with ``module_name``, ``importable``, and ``error`` (if any).
    """
    cmd = [sys.executable, "-c", f"import {module_name}"]
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
        }

    importable = proc.returncode == 0
    return {
        "module_name": module_name,
        "importable": importable,
        "error": "" if importable else proc.stderr.strip(),
    }
