"""
Asynchronous job submission and monitoring for FROGS tools.

- submit_job(): launches subprocess, returns job_id immediately (non-blocking)
- JobPoller: daemon thread that polls running processes and updates DB
- cancel_job(): sends SIGTERM
- build_command(): constructs the CLI command list from ToolSpec + params
"""
import os
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime
from typing import Optional

from config import (
    FROGS_BIN_DIR, FROGS_LIB_DIR, FROGS_PYTHON,
    WORKSPACE_ROOT, DEFAULT_NB_CPUS, POLL_INTERVAL_SEC,
)
from database import (
    init_db, insert_job, update_job_status, update_job_output_files,
    update_pipeline_step, get_job,
)
from tools_registry import TOOLS, ToolSpec, ParamSpec


# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

def _build_frogs_env() -> dict:
    """
    Build the environment for FROGS subprocesses.
    Replicates the PATH/PYTHONPATH setup each FROGS script does itself
    (prepending libexec to PATH and lib to PYTHONPATH).
    """
    env = os.environ.copy()

    # Prepend FROGS libexec to PATH
    existing_path = env.get("PATH", "")
    env["PATH"] = FROGS_BIN_DIR + os.pathsep + existing_path

    # Prepend FROGS lib to PYTHONPATH
    existing_pypath = env.get("PYTHONPATH", "")
    if existing_pypath:
        env["PYTHONPATH"] = FROGS_LIB_DIR + os.pathsep + existing_pypath
    else:
        env["PYTHONPATH"] = FROGS_LIB_DIR

    return env


FROGS_ENV = _build_frogs_env()


# ---------------------------------------------------------------------------
# Command builder
# ---------------------------------------------------------------------------

def build_command(tool_spec: ToolSpec, params: dict, job_dir: str) -> tuple[list[str], dict]:
    """
    Build the CLI command list and resolve output file paths.

    Returns:
        (command_list, resolved_output_files)
        resolved_output_files maps output_key -> absolute path in job_dir
    """
    param_map = {p.python_name: p for p in tool_spec.params}
    cmd = [FROGS_PYTHON, tool_spec.script_path]

    # Special case: reads_processing uses a positional subparser argument
    if tool_spec.has_subparser:
        subparser_val = params.get(tool_spec.subparser_param)
        if not subparser_val:
            raise ValueError(
                f"Tool '{tool_spec.name}' requires positional argument "
                f"'{tool_spec.subparser_param}' (e.g. 'illumina', 'longreads', '454')"
            )
        cmd.append(subparser_val)

    # Apply defaults from ToolSpec if not provided
    merged = {}
    for p in tool_spec.params:
        if p.python_name == tool_spec.subparser_param:
            continue  # already handled above
        if p.python_name in params:
            merged[p.python_name] = params[p.python_name]
        elif p.default is not None and p.is_output_file:
            # Use default output name (will be resolved to job_dir below)
            merged[p.python_name] = p.default

    # Resolve output file paths to absolute paths in job_dir
    resolved_outputs: dict[str, str] = {}
    for p in tool_spec.params:
        if not p.is_output_file or p.python_name not in merged:
            continue
        val = merged[p.python_name]
        if val and not os.path.isabs(val):
            val = os.path.join(job_dir, val)
            merged[p.python_name] = val
        if p.output_key and val:
            resolved_outputs[p.output_key] = val

    # nb_cpus default
    if "nb_cpus" in param_map and "nb_cpus" not in merged:
        merged["nb_cpus"] = DEFAULT_NB_CPUS

    # Build flag arguments
    for p in tool_spec.params:
        if p.python_name == tool_spec.subparser_param:
            continue
        if not p.cli_flag:
            continue

        val = merged.get(p.python_name)
        if val is None:
            continue

        if p.type == 'bool':
            if val:
                cmd.append(p.cli_flag)
        elif p.type == 'list':
            if isinstance(val, list):
                items = val
            else:
                # Accept space-separated string
                items = str(val).split()
            if items:
                cmd.append(p.cli_flag)
                cmd.extend(str(i) for i in items)
        else:
            cmd.append(p.cli_flag)
            cmd.append(str(val))

    return cmd, resolved_outputs


# ---------------------------------------------------------------------------
# Poller (daemon thread)
# ---------------------------------------------------------------------------

class JobPoller:
    """
    Daemon thread that polls active subprocess objects and updates DB
    when they complete.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # job_id -> (proc, project_id, step_name)
        self._active: dict[str, tuple[subprocess.Popen, Optional[str], Optional[str]]] = {}
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="JobPoller")
        self._thread.start()

    def register(self, job_id: str, proc: subprocess.Popen,
                 project_id: Optional[str], step_name: Optional[str]) -> None:
        with self._lock:
            self._active[job_id] = (proc, project_id, step_name)

    def _poll_loop(self) -> None:
        while True:
            time.sleep(POLL_INTERVAL_SEC)
            completed = []
            with self._lock:
                for job_id, (proc, project_id, step_name) in self._active.items():
                    rc = proc.poll()
                    if rc is not None:
                        completed.append((job_id, rc, project_id, step_name))
                for job_id, *_ in completed:
                    del self._active[job_id]

            for job_id, rc, project_id, step_name in completed:
                try:
                    status = "completed" if rc == 0 else "failed"
                    update_job_status(job_id, status, exit_code=rc)

                    # Scan output files and record which actually exist
                    job = get_job(job_id)
                    if job and job.get("output_files"):
                        existing = {
                            k: v for k, v in job["output_files"].items()
                            if isinstance(v, str) and os.path.isfile(v)
                        }
                        if existing != job["output_files"]:
                            update_job_output_files(job_id, existing)

                    if project_id and step_name:
                        update_pipeline_step(project_id, step_name, status, job_id)
                except Exception as exc:
                    print(f"[JobPoller] Error updating job {job_id}: {exc}", flush=True)


# Singleton poller started at import time
_poller = JobPoller()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def submit_job(tool_name: str, params: dict,
               project_id: Optional[str] = None,
               step_name: Optional[str] = None) -> str:
    """
    Submit a FROGS tool as a background subprocess.

    Args:
        tool_name: key in TOOLS registry
        params: dict of parameter values (python_name -> value)
        project_id: optional project to associate with
        step_name: optional pipeline step name

    Returns:
        job_id (str) — available immediately, job runs in background
    """
    tool_spec = TOOLS.get(tool_name)
    if tool_spec is None:
        raise ValueError(f"Unknown tool: '{tool_name}'. Run list_tools() to see available tools.")

    # Validate required params
    for p in tool_spec.params:
        if p.required and p.python_name not in params and p.python_name != tool_spec.subparser_param:
            raise ValueError(
                f"Tool '{tool_name}': required parameter '{p.python_name}' "
                f"(flag: {p.cli_flag}) is missing."
            )
    if tool_spec.has_subparser and tool_spec.subparser_param not in params:
        raise ValueError(
            f"Tool '{tool_name}': required positional parameter "
            f"'{tool_spec.subparser_param}' is missing."
        )

    job_id = str(uuid.uuid4())
    job_dir = os.path.join(WORKSPACE_ROOT, project_id or "standalone", job_id)
    os.makedirs(job_dir, exist_ok=True)

    # Build command and resolve outputs
    cmd, resolved_outputs = build_command(tool_spec, params, job_dir)

    # Output file paths for stdout/stderr capture
    stdout_file = os.path.join(job_dir, "stdout.txt")
    stderr_file = os.path.join(job_dir, "stderr.txt")

    # Find log file from resolved outputs (or default)
    log_file = resolved_outputs.get("log", os.path.join(job_dir, "frogs.log"))

    # Launch subprocess
    with open(stdout_file, "w") as fout, open(stderr_file, "w") as ferr:
        proc = subprocess.Popen(
            cmd,
            stdout=fout,
            stderr=ferr,
            cwd=job_dir,
            env=FROGS_ENV,
        )

    # Persist to DB
    insert_job(
        job_id=job_id,
        project_id=project_id,
        tool_name=tool_name,
        step_name=step_name,
        params=params,
        command=cmd,
        working_dir=job_dir,
        pid=proc.pid,
        stdout_file=stdout_file,
        stderr_file=stderr_file,
        log_file=log_file,
    )

    # Store anticipated output paths
    if resolved_outputs:
        update_job_output_files(job_id, resolved_outputs)

    # Register with poller
    _poller.register(job_id, proc, project_id, step_name)

    return job_id


def cancel_job(job_id: str) -> bool:
    """
    Send SIGTERM to the job's process.

    Returns True if the signal was sent, False if the process was not found.
    """
    job = get_job(job_id)
    if not job:
        raise ValueError(f"Job '{job_id}' not found.")

    pid = job.get("pid")
    if not pid:
        return False

    try:
        os.kill(pid, signal.SIGTERM)
        update_job_status(job_id, "cancelled", exit_code=-15)
        return True
    except ProcessLookupError:
        return False
    except PermissionError as exc:
        raise PermissionError(f"Cannot signal PID {pid}: {exc}") from exc
