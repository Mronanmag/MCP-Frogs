"""
Centralized configuration for the FROGS MCP server.
"""
import os
import shutil

# Base paths
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# FROGS installation directory.
# Priority: FROGS_DIR env var > bioconda default > legacy /app/FROGS
_FROGS_DIR = os.environ.get(
    "FROGS_DIR",
    os.path.join(_BASE_DIR, "FROGS"),
)

# FROGS tool directories — each can be overridden independently if needed.
FROGS_TOOLS_DIR = os.environ.get(
    "FROGS_TOOLS_DIR",
    os.path.join(_FROGS_DIR, "tools"),
)
FROGS_LIB_DIR = os.environ.get(
    "FROGS_LIB_DIR",
    os.path.join(_FROGS_DIR, "lib"),
)
FROGS_BIN_DIR = os.environ.get(
    "FROGS_BIN_DIR",
    os.path.join(_FROGS_DIR, "libexec"),
)

# MCP server paths
WORKSPACE_ROOT = os.path.join(_BASE_DIR, "workspaces")
DB_PATH = os.path.join(_BASE_DIR, "mcp_server", "frogs_jobs.db")

# FROGS Python interpreter (the conda env that has all FROGS dependencies)
FROGS_PYTHON = os.environ.get("FROGS_PYTHON", "/usr/bin/python3")

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

def validate_config() -> None:
    """Raise RuntimeError with actionable instructions if the config is invalid."""
    # Validate that FROGS_PYTHON points to a real, executable interpreter.
    if not (os.path.isfile(FROGS_PYTHON) and os.access(FROGS_PYTHON, os.X_OK)):
        # Try shutil.which as a fallback (handles bare names like "python3")
        resolved = shutil.which(FROGS_PYTHON)
        if resolved is None:
            raise RuntimeError(
                f"FROGS_PYTHON='{FROGS_PYTHON}' does not point to an executable Python "
                "interpreter.\n"
                "Fix: set the FROGS_PYTHON environment variable to the full path of the "
                "Python interpreter inside your FROGS conda environment, e.g.:\n"
                "  export FROGS_PYTHON=/path/to/conda/envs/frogs/bin/python3\n"
                "Then restart the MCP server."
            )

# Job management
DEFAULT_NB_CPUS = 4
POLL_INTERVAL_SEC = 10
