"""
FROGS MCP Server — exposes 13 tools via FastMCP (stdio transport).

Usage:
    python server.py

Or via MCP inspector:
    python -m mcp dev server.py
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from mcp.server.fastmcp import FastMCP

from config import WORKSPACE_ROOT
from database import (
    init_db,
    create_project as db_create_project,
    get_project,
    list_projects as db_list_projects,
    get_job,
    list_jobs as db_list_jobs,
    initialize_pipeline_steps,
    get_pipeline_steps,
)
from job_manager import submit_job as _submit_job, cancel_job as _cancel_job
from pipeline import (
    resolve_inputs_for_step,
    get_pipeline_recommendations as _get_recommendations,
    get_pipeline_status_summary,
)
from tools_registry import (
    TOOLS, PIPELINE_ORDER, OPTIONAL_STEPS, list_tool_names,
)

# Initialize DB on startup
init_db()

mcp = FastMCP("frogs", instructions="FROGS amplicon metagenomics pipeline manager")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_steps_ordered() -> list[dict]:
    """Return all steps in order with their metadata."""
    result = []
    for order, name in enumerate(PIPELINE_ORDER, start=1):
        result.append({"step_name": name, "step_order": order, "is_optional": False})
    for order, name in enumerate(OPTIONAL_STEPS, start=len(PIPELINE_ORDER) + 1):
        result.append({"step_name": name, "step_order": order, "is_optional": True})
    return result


def _elapsed(start_time: Optional[str], end_time: Optional[str] = None) -> Optional[float]:
    if not start_time:
        return None
    fmt = "%Y-%m-%dT%H:%M:%S.%f"
    fmt_short = "%Y-%m-%dT%H:%M:%S"
    def _parse(s):
        for f in (fmt, fmt_short):
            try:
                return datetime.strptime(s, f)
            except ValueError:
                continue
        return None
    t0 = _parse(start_time)
    if t0 is None:
        return None
    t1 = _parse(end_time) if end_time else datetime.utcnow()
    return (t1 - t0).total_seconds()


def _read_tail(path: str, n: int = 50) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except Exception as exc:
        return f"[Error reading {path}: {exc}]"


# ---------------------------------------------------------------------------
# Tool 1: submit_job
# ---------------------------------------------------------------------------

@mcp.tool()
def submit_job(
    tool_name: str,
    params: dict,
    project_id: Optional[str] = None,
) -> dict:
    """
    Submit any FROGS tool as a background job.

    Returns the job_id immediately (non-blocking). Use get_job_status() to
    check progress.

    Args:
        tool_name: Name of the FROGS tool (use list_tools() to see options).
        params: Dict of parameters. Keys are python_name (snake_case), e.g.
                {"input_fasta": "/path/to/seqs.fasta", "nb_cpus": 4}.
                For reads_processing, include {"sequencer": "illumina", ...}.
        project_id: Optional project to associate this job with.

    Returns:
        {"job_id": str, "status": "running", "working_dir": str}
    """
    job_id = _submit_job(tool_name, params, project_id=project_id)
    job = get_job(job_id)
    return {
        "job_id": job_id,
        "status": "running",
        "working_dir": job.get("working_dir", ""),
        "command": job.get("command", []),
    }


# ---------------------------------------------------------------------------
# Tool 2: get_job_status
# ---------------------------------------------------------------------------

@mcp.tool()
def get_job_status(job_id: str) -> dict:
    """
    Get the current status of a job.

    Returns:
        {"job_id", "tool_name", "status", "pid", "elapsed_seconds", "exit_code"}
    """
    job = get_job(job_id)
    if not job:
        return {"error": f"Job '{job_id}' not found."}

    return {
        "job_id": job_id,
        "tool_name": job.get("tool_name"),
        "step_name": job.get("step_name"),
        "status": job.get("status"),
        "pid": job.get("pid"),
        "elapsed_seconds": _elapsed(job.get("start_time"), job.get("end_time")),
        "exit_code": job.get("exit_code"),
        "working_dir": job.get("working_dir"),
    }


# ---------------------------------------------------------------------------
# Tool 3: get_job_results
# ---------------------------------------------------------------------------

@mcp.tool()
def get_job_results(job_id: str) -> dict:
    """
    Get the output files and last 50 lines of log for a completed job.

    Returns:
        {"job_id", "status", "output_files": {key: path}, "log_tail": str}
    """
    job = get_job(job_id)
    if not job:
        return {"error": f"Job '{job_id}' not found."}

    log_path = job.get("log_file") or job.get("stderr_file")
    log_tail = _read_tail(log_path, 50)

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "exit_code": job.get("exit_code"),
        "output_files": job.get("output_files") or {},
        "log_tail": log_tail,
        "working_dir": job.get("working_dir"),
    }


# ---------------------------------------------------------------------------
# Tool 4: list_jobs
# ---------------------------------------------------------------------------

@mcp.tool()
def list_jobs(project_id: Optional[str] = None) -> list[dict]:
    """
    List all jobs, optionally filtered by project.

    Returns a list of job summaries (job_id, tool_name, status, elapsed_seconds).
    """
    jobs = db_list_jobs(project_id)
    return [
        {
            "job_id": j["job_id"],
            "tool_name": j["tool_name"],
            "step_name": j.get("step_name"),
            "status": j["status"],
            "elapsed_seconds": _elapsed(j.get("start_time"), j.get("end_time")),
            "exit_code": j.get("exit_code"),
            "project_id": j.get("project_id"),
            "created_at": j.get("created_at"),
        }
        for j in jobs
    ]


# ---------------------------------------------------------------------------
# Tool 5: cancel_job
# ---------------------------------------------------------------------------

@mcp.tool()
def cancel_job(job_id: str) -> dict:
    """
    Cancel a running job by sending SIGTERM.

    FROGS tools handle cleanup of temporary files on SIGTERM.

    Returns:
        {"job_id", "cancelled": bool, "message": str}
    """
    try:
        sent = _cancel_job(job_id)
        return {
            "job_id": job_id,
            "cancelled": sent,
            "message": "SIGTERM sent." if sent else "Process not found (may have already finished).",
        }
    except ValueError as exc:
        return {"job_id": job_id, "cancelled": False, "message": str(exc)}
    except PermissionError as exc:
        return {"job_id": job_id, "cancelled": False, "message": str(exc)}


# ---------------------------------------------------------------------------
# Tool 6: create_project
# ---------------------------------------------------------------------------

@mcp.tool()
def create_project(
    name: str,
    description: str = "",
    working_dir: Optional[str] = None,
) -> dict:
    """
    Create a new analysis project and initialize pipeline step tracking.

    Args:
        name: Human-readable project name (e.g. "16S_soil_study_2024").
        description: Optional description.
        working_dir: Optional custom working directory (defaults to workspaces/<project_id>/).

    Returns:
        {"project_id", "name", "working_dir", "pipeline_steps": list}
    """
    project_id = str(uuid.uuid4())[:8]
    if not working_dir:
        working_dir = os.path.join(WORKSPACE_ROOT, project_id)
    os.makedirs(working_dir, exist_ok=True)

    project = db_create_project(
        project_id=project_id,
        name=name,
        description=description,
        working_dir=working_dir,
    )

    # Initialize all pipeline steps
    steps = _all_steps_ordered()
    initialize_pipeline_steps(project_id, steps)

    return {
        "project_id": project_id,
        "name": name,
        "description": description,
        "working_dir": working_dir,
        "created_at": project.get("created_at"),
        "pipeline_steps_initialized": len(steps),
        "message": (
            f"Project '{name}' created with ID '{project_id}'. "
            f"Use get_pipeline_recommendations('{project_id}') to start."
        ),
    }


# ---------------------------------------------------------------------------
# Tool 7: submit_pipeline_step
# ---------------------------------------------------------------------------

@mcp.tool()
def submit_pipeline_step(
    project_id: str,
    step_name: str,
    params: dict,
    auto_resolve_inputs: bool = True,
) -> dict:
    """
    Submit a named pipeline step for a project, with optional auto-resolution
    of input files from previous completed steps.

    Args:
        project_id: Project ID from create_project().
        step_name: Pipeline step name (e.g. "remove_chimera", "taxonomic_affiliation").
        params: Dict of parameters. Auto-resolved inputs are pre-populated; you
                can override them by passing explicit values.
        auto_resolve_inputs: If True (default), automatically fill input params
                             from outputs of completed previous steps.

    Returns:
        {"job_id", "step_name", "status", "resolved_inputs": dict, "working_dir": str}
    """
    project = get_project(project_id)
    if not project:
        return {"error": f"Project '{project_id}' not found. Run create_project() first."}

    tool_spec = TOOLS.get(step_name)
    if not tool_spec:
        return {"error": f"Unknown step '{step_name}'. Run list_tools() to see available tools."}

    resolved_inputs = {}
    if auto_resolve_inputs:
        resolved_inputs = resolve_inputs_for_step(project_id, step_name)

    # Merge: explicit params override auto-resolved
    merged_params = {**resolved_inputs, **params}

    job_id = _submit_job(
        tool_name=step_name,
        params=merged_params,
        project_id=project_id,
        step_name=step_name,
    )

    job = get_job(job_id)
    return {
        "job_id": job_id,
        "step_name": step_name,
        "status": "running",
        "resolved_inputs": resolved_inputs,
        "working_dir": job.get("working_dir", ""),
        "message": (
            f"Job {job_id} started for step '{step_name}'. "
            f"Check status with get_job_status('{job_id}')."
        ),
    }


# ---------------------------------------------------------------------------
# Tool 8: get_pipeline_status
# ---------------------------------------------------------------------------

@mcp.tool()
def get_pipeline_status(project_id: str) -> dict:
    """
    Get the full status of all pipeline steps for a project.

    Returns a structured summary with step statuses, counts, and next step.
    """
    project = get_project(project_id)
    if not project:
        return {"error": f"Project '{project_id}' not found."}

    summary = get_pipeline_status_summary(project_id)
    summary["project_name"] = project.get("name")
    return summary


# ---------------------------------------------------------------------------
# Tool 9: get_pipeline_recommendations
# ---------------------------------------------------------------------------

@mcp.tool()
def get_pipeline_recommendations(project_id: str) -> str:
    """
    ⭐ Main guidance tool. Returns a markdown report with:
    - Current pipeline status table
    - Next recommended step
    - Auto-resolved input file paths
    - List of still-required parameters
    - Ready-to-use submit_pipeline_step() call example

    Use this after each completed step to know what to run next.
    """
    project = get_project(project_id)
    if not project:
        return f"Error: Project '{project_id}' not found. Run create_project() first."
    return _get_recommendations(project_id)


# ---------------------------------------------------------------------------
# Tool 10: list_tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_tools(category: Optional[str] = None) -> list[dict]:
    """
    List all 28 available FROGS tools with descriptions and categories.

    Args:
        category: Optional filter (e.g. "Core pipeline", "Statistical analysis",
                  "Functional analysis", "Format conversion").

    Returns:
        List of {"name", "description", "category", "pipeline_step", "is_optional"}
    """
    result = []
    for name, spec in TOOLS.items():
        if category and spec.category.lower() != category.lower():
            continue
        result.append({
            "name": name,
            "description": spec.description,
            "category": spec.category,
            "pipeline_step": spec.pipeline_step,
            "is_optional": spec.is_optional,
            "script_path": spec.script_path,
        })
    return result


# ---------------------------------------------------------------------------
# Tool 11: get_tool_help
# ---------------------------------------------------------------------------

@mcp.tool()
def get_tool_help(tool_name: str) -> dict:
    """
    Get detailed parameter information for a specific FROGS tool.

    Returns:
        {"name", "description", "params": [{"python_name", "cli_flag", "required",
          "type", "default", "is_input_file", "is_output_file", "help_text"}]}
    """
    spec = TOOLS.get(tool_name)
    if not spec:
        return {
            "error": f"Tool '{tool_name}' not found.",
            "available": list_tool_names(),
        }

    params_info = []
    for p in spec.params:
        params_info.append({
            "python_name": p.python_name,
            "cli_flag": p.cli_flag,
            "required": p.required,
            "type": p.type,
            "default": p.default,
            "is_input_file": p.is_input_file,
            "is_output_file": p.is_output_file,
            "output_key": p.output_key,
            "help_text": p.help_text,
        })

    return {
        "name": spec.name,
        "description": spec.description,
        "category": spec.category,
        "pipeline_step": spec.pipeline_step,
        "is_optional": spec.is_optional,
        "has_subparser": spec.has_subparser,
        "subparser_param": spec.subparser_param if spec.has_subparser else None,
        "script_path": spec.script_path,
        "params": params_info,
    }


# ---------------------------------------------------------------------------
# Tool 12: list_projects
# ---------------------------------------------------------------------------

@mcp.tool()
def list_projects() -> list[dict]:
    """
    List all existing analysis projects.

    Returns:
        List of {"project_id", "name", "description", "working_dir", "created_at"}
    """
    projects = db_list_projects()
    result = []
    for p in projects:
        steps = get_pipeline_steps(p["project_id"])
        completed = sum(1 for s in steps if s["status"] == "completed")
        result.append({
            "project_id": p["project_id"],
            "name": p["name"],
            "description": p.get("description", ""),
            "working_dir": p.get("working_dir", ""),
            "created_at": p.get("created_at"),
            "steps_completed": completed,
            "steps_total": len(steps),
        })
    return result


# ---------------------------------------------------------------------------
# Tool 13: read_log
# ---------------------------------------------------------------------------

@mcp.tool()
def read_log(job_id: str, tail_lines: int = 100) -> str:
    """
    Read the log file for a job (FROGS log or stderr fallback).

    Args:
        job_id: Job ID.
        tail_lines: Number of lines from the end (default 100).

    Returns:
        Log content as plain text string.
    """
    job = get_job(job_id)
    if not job:
        return f"Error: Job '{job_id}' not found."

    # Try FROGS log file first, then stderr, then stdout
    for path_key in ("log_file", "stderr_file", "stdout_file"):
        path = job.get(path_key)
        if path and os.path.isfile(path):
            content = _read_tail(path, tail_lines)
            if content.strip():
                return f"[{path_key}: {path}]\n\n{content}"

    return f"No log content found for job '{job_id}' (working_dir: {job.get('working_dir')})."


# ---------------------------------------------------------------------------
# Tool 14: read_report
# ---------------------------------------------------------------------------

@mcp.tool()
def read_report(job_id: str) -> str:
    """
    Read the HTML report or TSV output from a job, stripped for LLM consumption.

    HTML reports are stripped of tags. TSV files show the first 50 lines.

    Returns:
        Report content as plain text.
    """
    job = get_job(job_id)
    if not job:
        return f"Error: Job '{job_id}' not found."

    output_files = job.get("output_files") or {}

    # Try HTML report
    for key in ("html",):
        path = output_files.get(key)
        if path and os.path.isfile(path):
            try:
                with open(path, "r", errors="replace") as f:
                    content = f.read()
                # Strip HTML tags (simple approach)
                import re
                text = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)
                text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
                return f"[HTML report: {path}]\n\n{text[:8000]}"
            except Exception as exc:
                return f"Error reading HTML: {exc}"

    # Try TSV outputs
    for key, path in output_files.items():
        if isinstance(path, str) and path.endswith(".tsv") and os.path.isfile(path):
            try:
                with open(path, "r", errors="replace") as f:
                    lines = f.readlines()[:50]
                return f"[TSV: {path}]\n\n{''.join(lines)}"
            except Exception as exc:
                return f"Error reading TSV: {exc}"

    return (
        f"No report file found for job '{job_id}'.\n"
        f"Available outputs: {list(output_files.keys())}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
