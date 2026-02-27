"""
Pipeline state machine and input resolution for FROGS.

Key concepts:
- FLOW_RULES: encodes the data flow between pipeline steps as a list of tuples
  (src_step, out_key, tgt_step, tgt_param)
- resolve_inputs_for_step(): scans completed jobs and populates input params
- get_pipeline_recommendations(): returns markdown guidance for Claude
"""
from typing import Optional

from database import get_pipeline_steps, list_jobs, get_project
from tools_registry import TOOLS, PIPELINE_ORDER, OPTIONAL_STEPS


# ---------------------------------------------------------------------------
# Data-flow rules: (src_step, output_key, tgt_step, tgt_param)
# ---------------------------------------------------------------------------
# Each tuple encodes: the output_key from src_step feeds tgt_param of tgt_step.
# A list of tuples avoids the silent duplicate-key problem of a plain dict.

FLOW_RULES: list[tuple[str, str, str, str]] = [
    # reads_processing -> remove_chimera
    ("reads_processing", "fasta", "remove_chimera", "input_fasta"),
    ("reads_processing", "biom",  "remove_chimera", "input_biom"),

    # remove_chimera -> cluster_filters
    ("remove_chimera", "fasta", "cluster_filters", "input_fasta"),
    ("remove_chimera", "biom",  "cluster_filters", "input_biom"),

    # cluster_filters -> taxonomic_affiliation AND affiliation_postprocess
    ("cluster_filters", "fasta", "taxonomic_affiliation",   "input_fasta"),
    ("cluster_filters", "biom",  "taxonomic_affiliation",   "input_biom"),
    ("cluster_filters", "fasta", "affiliation_postprocess", "input_fasta"),
    ("cluster_filters", "biom",  "affiliation_postprocess", "input_biom"),

    # taxonomic_affiliation -> affiliation_postprocess (biom with affiliations overrides)
    ("taxonomic_affiliation", "biom", "affiliation_postprocess", "input_biom"),

    # affiliation_postprocess -> affiliation_filters
    ("affiliation_postprocess", "fasta", "affiliation_filters", "input_fasta"),
    ("affiliation_postprocess", "biom",  "affiliation_filters", "input_biom"),

    # affiliation_filters -> affiliation_report, tree, normalisation
    ("affiliation_filters", "biom",  "affiliation_report", "input_biom"),
    ("affiliation_filters", "fasta", "tree",               "input_fasta"),
    ("affiliation_filters", "biom",  "tree",               "input_biom"),
    ("affiliation_filters", "fasta", "normalisation",      "input_fasta"),
    ("affiliation_filters", "biom",  "normalisation",      "input_biom"),

    # tree -> phyloseq_import
    ("tree", "tree", "phyloseq_import", "tree_nwk"),

    # normalisation -> phyloseq_import
    ("normalisation", "biom", "phyloseq_import", "input_biom"),

    # phyloseq_import -> all phyloseq analysis steps
    ("phyloseq_import", "rdata", "phyloseq_composition",    "phyloseq_rdata"),
    ("phyloseq_import", "rdata", "phyloseq_alpha_diversity", "phyloseq_rdata"),
    ("phyloseq_import", "rdata", "phyloseq_beta_diversity",  "phyloseq_rdata"),
    ("phyloseq_import", "rdata", "phyloseq_clustering",      "phyloseq_rdata"),
    ("phyloseq_import", "rdata", "phyloseq_structure",       "phyloseq_rdata"),
    ("phyloseq_import", "rdata", "phyloseq_manova",          "phyloseq_rdata"),
    ("phyloseq_import", "rdata", "deseq2_preprocess",        "phyloseq_rdata"),

    # phyloseq_beta_diversity -> clustering, structure, manova
    ("phyloseq_beta_diversity", "beta_matrix_dir", "phyloseq_clustering", "beta_distance_matrix"),
    ("phyloseq_beta_diversity", "beta_matrix_dir", "phyloseq_structure",  "beta_distance_matrix"),
    ("phyloseq_beta_diversity", "beta_matrix_dir", "phyloseq_manova",     "beta_distance_matrix"),

    # deseq2_preprocess -> deseq2_visualisation
    ("deseq2_preprocess", "deseq_rdata", "deseq2_visualisation", "deseq_rdata"),
    ("deseq2_preprocess", "rdata",       "deseq2_visualisation", "phyloseq_rdata"),

    # frogsfunc_placeseqs -> frogsfunc_functions
    ("frogsfunc_placeseqs", "fasta",           "frogsfunc_functions", "input_fasta"),
    ("frogsfunc_placeseqs", "biom",            "frogsfunc_functions", "input_biom"),
    ("frogsfunc_placeseqs", "tree",            "frogsfunc_functions", "input_tree"),
    ("frogsfunc_placeseqs", "marker_copy_tsv", "frogsfunc_functions", "input_marker_copy"),
]

# Build target-step lookup for fast access: tgt_step -> list of (src_step, out_key, tgt_param)
_RULES_BY_TARGET: dict[str, list[tuple[str, str, str]]] = {}
for _src, _out, _tgt, _param in FLOW_RULES:
    _RULES_BY_TARGET.setdefault(_tgt, []).append((_src, _out, _param))

# Shorthand resolution: output_key suffix -> common input param names
# Used as fallback when explicit mapping isn't found
_OUTPUT_KEY_TO_INPUT_PARAM: dict[str, str] = {
    "fasta":   "input_fasta",
    "biom":    "input_biom",
    "rdata":   "phyloseq_rdata",
    "tree":    "tree_nwk",
    "tsv":     "input_tsv",
    "compo":   "input_compo",
}


def _get_completed_jobs_for_project(project_id: str) -> list[dict]:
    """Return all completed jobs for a project, ordered by start_time."""
    jobs = list_jobs(project_id)
    return [j for j in jobs if j.get("status") == "completed"
            and j.get("output_files")]


def resolve_inputs_for_step(project_id: str, step_name: str) -> dict:
    """
    Scan all completed jobs for this project and auto-populate input params
    for the given step based on FLOW_RULES and shorthand fallback.

    Later completed jobs overwrite earlier ones (more recent output preferred).

    Returns:
        dict of python_name -> absolute file path
    """
    tool_spec = TOOLS.get(step_name)
    if not tool_spec:
        return {}

    completed_jobs = _get_completed_jobs_for_project(project_id)
    if not completed_jobs:
        return {}

    # Build indexes from completed job outputs
    # full_index: "src_step.out_key" -> path  (most recent wins)
    # key_index:  "out_key" -> path           (most recent wins, any step)
    full_index: dict[str, str] = {}
    key_index: dict[str, str] = {}
    for job in sorted(completed_jobs, key=lambda j: j.get("start_time", "")):
        src_step = job.get("step_name", "")
        outputs = job.get("output_files") or {}
        for out_key, path in outputs.items():
            if path and isinstance(path, str):
                full_index[f"{src_step}.{out_key}"] = path
                key_index[out_key] = path

    resolved: dict[str, str] = {}
    target_input_params = {p.python_name for p in tool_spec.params if p.is_input_file}

    # Apply explicit FLOW_RULES for this target step
    for src_step, out_key, tgt_param in _RULES_BY_TARGET.get(step_name, []):
        if tgt_param not in target_input_params:
            continue
        full_key = f"{src_step}.{out_key}"
        if full_key in full_index:
            resolved[tgt_param] = full_index[full_key]
        elif out_key in key_index:
            # Fallback: any completed step that produced this output_key
            resolved[tgt_param] = key_index[out_key]

    # Shorthand fallback for remaining unresolved inputs
    for param_name in target_input_params:
        if param_name in resolved:
            continue
        for key_suffix, generic_input in _OUTPUT_KEY_TO_INPUT_PARAM.items():
            if generic_input == param_name and key_suffix in key_index:
                resolved[param_name] = key_index[key_suffix]
                break

    return resolved


def get_pipeline_status_summary(project_id: str) -> dict:
    """
    Return a structured summary of all pipeline steps for a project.
    """
    steps = get_pipeline_steps(project_id)
    step_by_name = {s["step_name"]: s for s in steps}

    summary = {
        "project_id": project_id,
        "steps": steps,
        "completed_count": sum(1 for s in steps if s["status"] == "completed"),
        "failed_count": sum(1 for s in steps if s["status"] == "failed"),
        "running_count": sum(1 for s in steps if s["status"] == "running"),
        "pending_count": sum(1 for s in steps if s["status"] == "pending"),
        "total_count": len(steps),
    }

    # Determine next recommended step
    all_steps = PIPELINE_ORDER + OPTIONAL_STEPS
    for step_name in PIPELINE_ORDER:
        info = step_by_name.get(step_name, {})
        status = info.get("status", "unknown")
        if status in ("pending", "unknown"):
            summary["next_step"] = step_name
            break
    else:
        summary["next_step"] = None

    return summary


def get_pipeline_recommendations(project_id: str) -> str:
    """
    Return a markdown string for Claude guiding the next analysis step.
    """
    project = get_project(project_id)
    if not project:
        return f"❌ Project '{project_id}' not found."

    steps = get_pipeline_steps(project_id)
    if not steps:
        return (
            f"## Project: {project['name']}\n\n"
            "No pipeline steps initialized. Use `create_project()` to set up the pipeline.\n"
        )

    step_by_name = {s["step_name"]: s for s in steps}

    lines = [f"## Pipeline Status: {project['name']}\n"]

    # Status table
    lines.append("| Step | Order | Status | Optional |")
    lines.append("|------|-------|--------|----------|")
    for step in sorted(steps, key=lambda s: s["step_order"]):
        status_emoji = {
            "completed": "✅",
            "running": "🔄",
            "failed": "❌",
            "pending": "⏳",
        }.get(step["status"], "❓")
        opt = "Yes" if step["is_optional"] else "No"
        lines.append(
            f"| {step['step_name']} | {step['step_order']} "
            f"| {status_emoji} {step['status']} | {opt} |"
        )

    lines.append("")

    # Find next pending step in main pipeline
    next_step = None
    for step_name in PIPELINE_ORDER:
        info = step_by_name.get(step_name, {})
        if info.get("status", "pending") in ("pending", "unknown"):
            next_step = step_name
            break

    if next_step is None:
        lines.append("### 🎉 Main pipeline complete!\n")
        lines.append("Consider running optional analysis steps:")
        for step_name in OPTIONAL_STEPS:
            info = step_by_name.get(step_name, {})
            if info.get("status", "pending") == "pending":
                lines.append(f"  - `{step_name}`")
        return "\n".join(lines)

    lines.append(f"### ▶️ Next recommended step: `{next_step}`\n")

    # Resolve inputs
    tool_spec = TOOLS.get(next_step)
    resolved = resolve_inputs_for_step(project_id, next_step)

    if resolved:
        lines.append("**Auto-resolved inputs:**")
        for param, path in resolved.items():
            lines.append(f"  - `{param}` = `{path}`")
        lines.append("")

    # Show required params that still need values
    if tool_spec:
        missing_required = []
        for p in tool_spec.params:
            if p.required and p.python_name not in resolved and not p.is_output_file:
                missing_required.append(p)

        if missing_required:
            lines.append("**Still required (must provide):**")
            for p in missing_required:
                lines.append(
                    f"  - `{p.python_name}` ({p.cli_flag}) — {p.help_text}"
                )
            lines.append("")

        # Example call
        lines.append("**Submit with:**")
        example_params = dict(resolved)
        for p in missing_required:
            example_params[p.python_name] = f"<{p.python_name}>"
        lines.append(
            f"```\nsubmit_pipeline_step(\n"
            f"  project_id='{project_id}',\n"
            f"  step_name='{next_step}',\n"
            f"  params={example_params}\n"
            f")\n```"
        )

    return "\n".join(lines)
