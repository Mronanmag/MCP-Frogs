"""
Centralized configuration for the FROGS MCP server.
"""
import os

# Base paths
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FROGS_DIR = os.path.join(_BASE_DIR, "FROGS")

# FROGS tool directories
FROGS_TOOLS_DIR = os.path.join(_FROGS_DIR, "tools")
FROGS_LIB_DIR = os.path.join(_FROGS_DIR, "lib")
FROGS_BIN_DIR = os.path.join(_FROGS_DIR, "libexec")

# MCP server paths
WORKSPACE_ROOT = os.path.join(_BASE_DIR, "workspaces")
DB_PATH = os.path.join(_BASE_DIR, "mcp_server", "frogs_jobs.db")

# FROGS Python interpreter (the conda env that has all FROGS dependencies)
FROGS_PYTHON = os.environ.get("FROGS_PYTHON", "/usr/bin/python3")

# Job management
DEFAULT_NB_CPUS = 4
POLL_INTERVAL_SEC = 10
