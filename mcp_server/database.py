"""
SQLite database operations for the FROGS MCP server.
All state is persisted here, enabling job tracking across sessions.
"""
import sqlite3
import json
from datetime import datetime
from typing import Optional

from config import DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    import os
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = _connect()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id   TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                description  TEXT,
                working_dir  TEXT,
                created_at   TEXT NOT NULL,
                metadata     TEXT
            );

            CREATE TABLE IF NOT EXISTS jobs (
                job_id       TEXT PRIMARY KEY,
                project_id   TEXT REFERENCES projects(project_id),
                tool_name    TEXT NOT NULL,
                step_name    TEXT,
                params       TEXT,
                command      TEXT,
                status       TEXT NOT NULL DEFAULT 'pending',
                pid          INTEGER,
                start_time   TEXT,
                end_time     TEXT,
                exit_code    INTEGER,
                stdout_file  TEXT,
                stderr_file  TEXT,
                log_file     TEXT,
                output_files TEXT,
                working_dir  TEXT,
                created_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pipeline_steps (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   TEXT NOT NULL REFERENCES projects(project_id),
                step_name    TEXT NOT NULL,
                step_order   INTEGER NOT NULL,
                job_id       TEXT REFERENCES jobs(job_id),
                status       TEXT NOT NULL DEFAULT 'pending',
                is_optional  INTEGER NOT NULL DEFAULT 0,
                UNIQUE(project_id, step_name)
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def create_project(project_id: str, name: str, description: str = "",
                   working_dir: str = "", metadata: dict = None) -> dict:
    conn = _connect()
    try:
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO projects (project_id, name, description, working_dir, created_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, name, description, working_dir, now,
             json.dumps(metadata or {}))
        )
        conn.commit()
        return get_project(project_id)
    finally:
        conn.close()


def get_project(project_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def list_projects() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def insert_job(job_id: str, project_id: Optional[str], tool_name: str,
               step_name: Optional[str], params: dict, command: list,
               working_dir: str, pid: Optional[int] = None,
               stdout_file: str = "", stderr_file: str = "",
               log_file: str = "") -> dict:
    conn = _connect()
    try:
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT INTO jobs (job_id, project_id, tool_name, step_name, params,
                                 command, status, pid, start_time, stdout_file,
                                 stderr_file, log_file, working_dir, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, project_id, tool_name, step_name,
             json.dumps(params), json.dumps(command),
             pid, now, stdout_file, stderr_file, log_file, working_dir, now)
        )
        conn.commit()
        return get_job(job_id)
    finally:
        conn.close()


def update_job_status(job_id: str, status: str, exit_code: Optional[int] = None) -> None:
    conn = _connect()
    try:
        now = datetime.utcnow().isoformat()
        conn.execute(
            """UPDATE jobs SET status = ?, exit_code = ?, end_time = ?
               WHERE job_id = ?""",
            (status, exit_code, now, job_id)
        )
        conn.commit()
    finally:
        conn.close()


def update_job_output_files(job_id: str, output_files: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE jobs SET output_files = ? WHERE job_id = ?",
            (json.dumps(output_files), job_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_job(job_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        # Deserialize JSON fields
        for field in ("params", "command", "output_files"):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d
    finally:
        conn.close()


def list_jobs(project_id: Optional[str] = None) -> list[dict]:
    conn = _connect()
    try:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            for field in ("params", "command", "output_files"):
                if d.get(field):
                    try:
                        d[field] = json.loads(d[field])
                    except (json.JSONDecodeError, TypeError):
                        pass
            result.append(d)
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def initialize_pipeline_steps(project_id: str, steps: list[dict]) -> None:
    """
    steps: list of {"step_name": str, "step_order": int, "is_optional": bool}
    """
    conn = _connect()
    try:
        conn.executemany(
            """INSERT OR IGNORE INTO pipeline_steps
               (project_id, step_name, step_order, status, is_optional)
               VALUES (?, ?, ?, 'pending', ?)""",
            [(project_id, s["step_name"], s["step_order"], int(s.get("is_optional", False)))
             for s in steps]
        )
        conn.commit()
    finally:
        conn.close()


def update_pipeline_step(project_id: str, step_name: str,
                         status: str, job_id: Optional[str] = None) -> None:
    conn = _connect()
    try:
        if job_id:
            conn.execute(
                """UPDATE pipeline_steps SET status = ?, job_id = ?
                   WHERE project_id = ? AND step_name = ?""",
                (status, job_id, project_id, step_name)
            )
        else:
            conn.execute(
                """UPDATE pipeline_steps SET status = ?
                   WHERE project_id = ? AND step_name = ?""",
                (status, project_id, step_name)
            )
        conn.commit()
    finally:
        conn.close()


def get_pipeline_steps(project_id: str) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT ps.*, j.status as job_status, j.start_time, j.end_time, j.exit_code
               FROM pipeline_steps ps
               LEFT JOIN jobs j ON ps.job_id = j.job_id
               WHERE ps.project_id = ?
               ORDER BY ps.step_order""",
            (project_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
