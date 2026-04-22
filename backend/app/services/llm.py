"""
LLM service — OpenAI-compatible client with tool definitions for job data access.

Provider is configured via LLM_BASE_URL / LLM_MODEL / LLM_API_KEY. Any
OpenAI-compatible endpoint works (Anthropic, Modal vLLM, Ollama, etc.).

Tools give the LLM structured access to job results without pre-loading
everything into the prompt. Add new tools to TOOLS and _EXECUTORS.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import AsyncIterator

import sqlalchemy as sa

from .chat_artifacts import create_chat_figure_artifact
from .chat_state import ChatScope, ChatToolCall, ChatTurn, new_turn_id, utc_now

logger = logging.getLogger(__name__)
_SANDBOX_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(sandbox:[^)]+\)")


@dataclass
class ToolExecutionResult:
    content: str
    parsed: object = None
    artifacts: list = field(default_factory=list)

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling schema)
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_jobs",
            "description": (
                "List the user's completed benchmark jobs. Returns job ID, model name, "
                "region, dataset ID, and completion time. Use this to discover what "
                "runs are available before fetching metrics."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_info",
            "description": (
                "Get configuration details for a specific job: model name, region, "
                "obs dataset, ROMP parameters (start/end date, climatology years, etc.)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The job UUID"},
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_metrics",
            "description": (
                "Get aggregate spatial statistics for a completed job. Returns mean, "
                "min, max, and percentiles (p25/p50/p75/p90) for each metric "
                "(false_alarm_rate, miss_rate, mean_mae) across all forecast windows. "
                "Use this to compare model skill across jobs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The job UUID"},
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spatial_summary",
            "description": (
                "Get the spatial distribution of a specific metric for a job. "
                "Returns per-gridpoint statistics showing where the model performs "
                "well or poorly geographically. Useful for identifying regional biases."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The job UUID"},
                    "model": {"type": "string", "description": "Model name (e.g. 'aifs')"},
                    "window": {"type": "string", "description": "Forecast window (e.g. '16-30')"},
                    "metric": {
                        "type": "string",
                        "enum": ["false_alarm_rate", "miss_rate", "mean_mae"],
                        "description": "Metric to summarise",
                    },
                },
                "required": ["job_id", "model", "window", "metric"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_code_sandbox",
            "description": (
                "Run arbitrary Python code in an isolated sandbox with no network access. "
                "Use this for general computation — statistics, simulations, cross-tabulations — "
                "when you don't need job NC files. "
                "You must define a function `def compute() -> dict` that returns a JSON-serialisable dict. "
                "Available libraries: xarray, numpy, scipy, pandas, matplotlib.\n\n"
                "To produce a plot, use matplotlib with the Agg backend and the provided "
                "`save_figure(fig, filename='figure.webp', format='webp')` helper. "
                "Do not use BytesIO, base64, `fig.savefig` to a buffer, or return keys like "
                "`image`, `image_data`, `figure`, or `figure_data`. "
                "Return artifact metadata under an `artifacts` key:\n"
                "```python\n"
                "import matplotlib\n"
                "matplotlib.use('Agg')\n"
                "import matplotlib.pyplot as plt\n"
                "\n"
                "def compute() -> dict:\n"
                "    fig, ax = plt.subplots()\n"
                "    ax.plot([1, 2, 3], [4, 5, 6])\n"
                "    artifact = save_figure(fig, filename='plot.webp', format='webp')\n"
                "    plt.close(fig)\n"
                "    return {'artifacts': [artifact]}\n"
                "```"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": (
                            "Python source defining `def compute() -> dict`. "
                            "Must be self-contained. To return a plot, use save_figure(...) and "
                            "return the resulting metadata under an 'artifacts' key. Do not "
                            "encode images manually or return base64/image_data fields."
                        ),
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_code",
            "description": (
                "Execute custom Python analysis code against the NC output files for a job. "
                "Use this when the built-in metrics don't answer the question — e.g. to compute "
                "a custom metric, build a histogram, or cross-tabulate results. "
                "The code runs in an isolated sandbox with no network access. "
                "You must define a function `def compute(nc_dir: str) -> dict` that opens the "
                "NC files in `nc_dir` using xarray/numpy and returns a JSON-serialisable dict. "
                "Available libraries: xarray, numpy, scipy, pandas, h5netcdf, matplotlib.\n\n"
                "To produce a plot, use matplotlib with the Agg backend and the provided "
                "`save_figure(fig, filename='figure.webp', format='webp')` helper. "
                "Do not use BytesIO, base64, `fig.savefig` to a buffer, or return keys like "
                "`image`, `image_data`, `figure`, or `figure_data`. "
                "Return artifact metadata under an `artifacts` key:\n"
                "```python\n"
                "import matplotlib\n"
                "matplotlib.use('Agg')\n"
                "import matplotlib.pyplot as plt\n"
                "\n"
                "def compute(nc_dir: str) -> dict:\n"
                "    # ... load data from nc_dir ...\n"
                "    fig, ax = plt.subplots()\n"
                "    ax.plot(windows, mae_values)\n"
                "    artifact = save_figure(fig, filename='plot.webp', format='webp')\n"
                "    plt.close(fig)\n"
                "    return {'artifacts': [artifact]}\n"
                "```\n"
                "Returns the dict your function returns, or an error message."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The job UUID"},
                    "code": {
                        "type": "string",
                        "description": (
                            "Python source defining `def compute(nc_dir: str) -> dict`. "
                            "Must be self-contained (no imports outside the stdlib + xarray/numpy/scipy/pandas/matplotlib). "
                            "To return a plot, use save_figure(...) and return the resulting metadata "
                            "under an 'artifacts' key. Do not encode images manually or return "
                            "base64/image_data fields."
                        ),
                    },
                },
                "required": ["job_id", "code"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are an expert in AI weather prediction and monsoon onset forecasting, \
helping researchers interpret benchmark results from ROMP (Rainfall Onset Metrics Package).

## Domain knowledge

ROMP evaluates how well AI weather prediction (AIWP) models forecast monsoon onset dates \
compared to observed climatology. Key metrics:

- **mean_mae**: Mean Absolute Error in days between predicted and observed onset date. \
Lower is better. Values under 5 days indicate strong skill; over 15 days indicates poor skill.
- **false_alarm_rate (FAR)**: Fraction of predicted onsets that did not correspond to a real \
onset. Higher means more false alarms.
- **miss_rate (MR)**: Fraction of real onsets the model failed to detect. Higher means more \
missed events.

Forecast windows (e.g. "1-15", "16-30") are lead-time ranges in days. Shorter windows are \
easier; longer windows test extended-range skill. Always compare model metrics against the \
climatology baseline — skill is only meaningful relative to that reference.

## Approach

- Use tools to fetch only the data needed for the question. Do not dump all available metrics \
into the response unprompted.
- Think before fetching: identify what data is required, then make targeted tool calls.
- If a question is ambiguous, ask one clarifying question rather than guessing.
- State uncertainty clearly. Do not overinterpret noisy or sparse metrics.
- Use `run_code` when the built-in metrics don't answer the question — e.g. computing a custom \
statistic, comparing distributions, cross-tabulating results, or producing a chart. The sandbox \
has xarray, numpy, scipy, pandas, and matplotlib. The NC files in `nc_dir` are the \
spatial_metrics_*.nc output files. Always handle missing values (NaN) explicitly in your code.
- When a chart would communicate the result more clearly than a table or prose, produce one using \
matplotlib. Always use `matplotlib.use('Agg')` before importing pyplot, call \
`artifact = save_figure(fig, filename='plot.webp', format='webp')`, return it under \
`{'artifacts': [artifact]}`, and call `plt.close(fig)` after saving.
- Never manually base64-encode an image, never use `BytesIO` for chart transport, and never \
return keys like `image`, `image_data`, `figure`, or `figure_data`. If you want to return a \
chart, the only supported mechanism is `save_figure(...)` plus the `artifacts` list.

## Output style

- Do not narrate tool use. Never say "Let me fetch…", "I'll now retrieve…", or similar. \
Just call the tools and lead with findings.
- No sycophantic openers ("Great question!") or closing fluff ("I hope this helps!").
- Lead with the answer or key finding, then support it with data.
- Use markdown: bold for key numbers, tables for model comparisons, headers only for \
multi-section responses.
- Be concise. These are researchers who understand statistics — skip obvious interpretation \
and get to the insight.
- When uncertain about what a metric value means in context, say so explicitly."""


# ---------------------------------------------------------------------------
# Tool executors
# ---------------------------------------------------------------------------

def _scope_conditions(scope: ChatScope, jobs_table: sa.Table) -> list:
    """Return a list of SQLAlchemy WHERE-clause expressions for the given scope."""
    if scope.kind == "benchmark_run_group":
        if scope.job_ids:
            return [sa.or_(
                jobs_table.c.run_id == sa.bindparam("scope_key"),
                jobs_table.c.id.in_(sa.bindparam("job_ids", expanding=True)),
            )]
        return [jobs_table.c.run_id == sa.bindparam("scope_key")]
    if scope.job_ids:
        return [jobs_table.c.id.in_(sa.bindparam("job_ids", expanding=True))]
    return []


def _scope_params(scope: ChatScope) -> dict:
    """Return bind-parameter values that correspond to _scope_conditions."""
    params: dict = {}
    if scope.kind == "benchmark_run_group":
        params["scope_key"] = scope.key
    if scope.job_ids:
        params["job_ids"] = scope.job_ids
    return params


# Lightweight table reference for building typed WHERE clauses.
_jobs = sa.table(
    "jobs",
    sa.column("id"),
    sa.column("user_id"),
    sa.column("status"),
    sa.column("run_id"),
    sa.column("config_json"),
    sa.column("completed_at"),
    sa.column("created_at"),
)


async def _exec_list_jobs(args: dict, user_id: str, scope: ChatScope) -> str:
    from ..database import get_db

    query = (
        sa.select(_jobs.c.id, _jobs.c.config_json, _jobs.c.status, _jobs.c.completed_at, _jobs.c.created_at)
        .where(_jobs.c.user_id == sa.bindparam("uid"))
        .where(_jobs.c.status == "complete")
    )
    for cond in _scope_conditions(scope, _jobs):
        query = query.where(cond)
    query = query.order_by(_jobs.c.completed_at.desc())

    async with get_db() as conn:
        rows = (await conn.execute(query, {"uid": user_id, **_scope_params(scope)})).mappings().fetchall()
        rows = [dict(r) for r in rows]
    jobs = []
    for r in rows:
        cfg = json.loads(r.get("config_json") or "{}")
        jobs.append({
            "job_id": r["id"],
            "model_name": cfg.get("model_name"),
            "region": cfg.get("romp_params", {}).get("region"),
            "dataset_id": cfg.get("dataset_id") or r.get("dataset_id"),
            "completed_at": r["completed_at"],
        })
    return json.dumps(jobs)


async def _exec_get_job_info(args: dict, user_id: str, scope: ChatScope) -> str:
    from ..database import get_db

    job_id = args["job_id"]
    query = (
        sa.select(_jobs.c.config_json, _jobs.c.status)
        .where(_jobs.c.id == sa.bindparam("id"))
        .where(_jobs.c.user_id == sa.bindparam("uid"))
    )
    for cond in _scope_conditions(scope, _jobs):
        query = query.where(cond)

    async with get_db() as conn:
        row = (await conn.execute(query, {"id": job_id, "uid": user_id, **_scope_params(scope)})).mappings().fetchone()
        row = dict(row) if row else None
    if not row:
        return json.dumps({"error": f"Job {job_id} not found"})
    cfg = json.loads(row.get("config_json") or "{}")
    return json.dumps({
        "job_id": job_id,
        "status": row["status"],
        "model_name": cfg.get("model_name"),
        "model_dir": cfg.get("model_dir"),
        "obs_dir": cfg.get("obs_dir"),
        "romp_params": cfg.get("romp_params", {}),
    })


def _job_status_query(scope: ChatScope):
    """Build a SELECT status query for a single job filtered by scope."""
    query = (
        sa.select(_jobs.c.status)
        .where(_jobs.c.id == sa.bindparam("id"))
        .where(_jobs.c.user_id == sa.bindparam("uid"))
    )
    for cond in _scope_conditions(scope, _jobs):
        query = query.where(cond)
    return query


async def _exec_get_job_metrics(args: dict, user_id: str, scope: ChatScope) -> str:
    import numpy as np
    from ..database import get_db
    from ..services.storage import get_storage

    job_id = args["job_id"]

    async with get_db() as conn:
        row = (await conn.execute(
            _job_status_query(scope),
            {"id": job_id, "uid": user_id, **_scope_params(scope)},
        )).mappings().fetchone()
        row = dict(row) if row else None
    if not row:
        return json.dumps({"error": f"Job {job_id} not found"})
    if row["status"] != "complete":
        return json.dumps({"error": f"Job {job_id} is not complete"})

    def _load():
        import xarray as xr
        storage = get_storage()
        UNIT_MAP = {"false_alarm_rate": "fraction", "miss_rate": "fraction"}

        if storage.is_local:
            output_dir = storage._outputs_dir / job_id / "output"
            nc_files = sorted(output_dir.glob("spatial_metrics_*.nc")) if output_dir.exists() else []
        else:
            import gcsfs
            fs = gcsfs.GCSFileSystem()
            prefix = f"{storage._outputs_bucket}/{job_id}/output/spatial_metrics_"
            nc_files = [f"gs://{f}" for f in sorted(fs.glob(f"{prefix}*.nc"))]

        def _open(path):
            if storage.is_local:
                return xr.open_dataset(path)
            with fs.open(str(path).removeprefix("gs://"), "rb") as f:
                return xr.load_dataset(f, engine="h5netcdf")

        windows = []
        for nc in nc_files:
            ds = _open(nc)
            model = str(ds.attrs.get("model", ""))
            window = str(ds.attrs.get("verification_window", "")).replace(",", "-")
            metrics = {}
            for var in ds.data_vars:
                arr = ds[var].values.astype(float)
                valid = arr[~np.isnan(arr)]
                if len(valid) == 0:
                    continue
                var_str = str(var)
                metrics[var_str] = {
                    "mean": round(float(np.mean(valid)), 4),
                    "p50": round(float(np.percentile(valid, 50)), 4),
                    "p90": round(float(np.percentile(valid, 90)), 4),
                    "min": round(float(np.min(valid)), 4),
                    "max": round(float(np.max(valid)), 4),
                    "unit": UNIT_MAP.get(var_str, "days"),
                }
            ds.close()
            windows.append({"model": model, "window": window, "metrics": metrics})
        windows.sort(key=lambda w: (w["model"] == "climatology", w["window"]))
        return windows

    windows = await asyncio.to_thread(_load)
    return json.dumps({"job_id": job_id, "windows": windows})


async def _exec_get_spatial_summary(args: dict, user_id: str, scope: ChatScope) -> str:
    import numpy as np
    from ..database import get_db
    from ..services.storage import get_storage

    job_id = args["job_id"]
    model = args["model"]
    window = args["window"]
    metric = args["metric"]

    async with get_db() as conn:
        row = (await conn.execute(
            _job_status_query(scope),
            {"id": job_id, "uid": user_id, **_scope_params(scope)},
        )).mappings().fetchone()
        row = dict(row) if row else None
    if not row:
        return json.dumps({"error": f"Job {job_id} not found"})
    if row["status"] != "complete":
        return json.dumps({"error": f"Job {job_id} is not complete"})

    def _load():
        import xarray as xr
        storage = get_storage()
        w_alt = window.replace("-", ",")

        if storage.is_local:
            output_dir = storage._outputs_dir / job_id / "output"
            matches = list(output_dir.glob(f"spatial_metrics_{model}_{window}.nc"))
            if not matches:
                matches = list(output_dir.glob(f"spatial_metrics_{model}_{w_alt}.nc"))
        else:
            import gcsfs
            fs = gcsfs.GCSFileSystem()
            base = f"{storage._outputs_bucket}/{job_id}/output"
            matches = fs.glob(f"{base}/spatial_metrics_{model}_{window}.nc")
            if not matches:
                matches = fs.glob(f"{base}/spatial_metrics_{model}_{w_alt}.nc")
            matches = [f"gs://{f}" for f in matches]

        if not matches:
            return {"error": f"No grid file found for {model}/{window}"}

        if storage.is_local:
            ds = xr.open_dataset(matches[0])
        else:
            with fs.open(str(matches[0]).removeprefix("gs://"), "rb") as f:
                ds = xr.load_dataset(f, engine="h5netcdf")

        if metric not in ds.data_vars:
            ds.close()
            return {"error": f"Metric {metric!r} not in dataset"}

        arr = ds[metric].values.astype(float)
        valid = arr[~np.isnan(arr)]
        lats = ds.lat.values.tolist()
        lons = ds.lon.values.tolist()
        ds.close()

        if len(valid) == 0:
            return {"error": "No valid data points"}

        return {
            "job_id": job_id, "model": model, "window": window, "metric": metric,
            "grid_shape": {"lats": len(lats), "lons": len(lons)},
            "lat_range": [round(min(lats), 2), round(max(lats), 2)],
            "lon_range": [round(min(lons), 2), round(max(lons), 2)],
            "valid_points": int(len(valid)),
            "stats": {
                "mean": round(float(np.mean(valid)), 4),
                "p25": round(float(np.percentile(valid, 25)), 4),
                "p50": round(float(np.percentile(valid, 50)), 4),
                "p75": round(float(np.percentile(valid, 75)), 4),
                "p90": round(float(np.percentile(valid, 90)), 4),
                "min": round(float(np.min(valid)), 4),
                "max": round(float(np.max(valid)), 4),
            },
        }

    result = await asyncio.to_thread(_load)
    return json.dumps(result)


async def _exec_run_code_sandbox(args: dict, user_id: str, scope: ChatScope) -> str:
    import asyncio

    code = args["code"]

    def _run():
        import modal
        fn = modal.Function.from_name("almanac-romp", "run_code_sandbox")
        return fn.remote(code)

    try:
        result = await asyncio.to_thread(_run)
        return result
    except Exception as exc:
        logger.exception("run_code_sandbox failed")
        return {"ok": False, "error": str(exc)}


async def _exec_run_code(args: dict, user_id: str, scope: ChatScope) -> str:
    from ..database import get_db
    from ..services.storage import get_storage

    job_id = args["job_id"]
    code = args["code"]

    async with get_db() as conn:
        row = (await conn.execute(
            _job_status_query(scope),
            {"id": job_id, "uid": user_id, **_scope_params(scope)},
        )).mappings().fetchone()
        row = dict(row) if row else None
    if not row:
        return json.dumps({"error": f"Job {job_id} not found"})
    if row["status"] != "complete":
        return json.dumps({"error": f"Job {job_id} is not complete"})

    storage = get_storage()
    if storage.is_local:
        return json.dumps({"error": "run_code requires GCS storage — not available in local dev mode"})

    def _run():
        import modal
        fn = modal.Function.from_name("almanac-romp", "run_code")
        return fn.remote(job_id, storage._outputs_bucket, code)

    try:
        result = await asyncio.to_thread(_run)
        return result
    except Exception as exc:
        logger.exception("run_code sandbox failed")
        return {"ok": False, "error": str(exc)}


# Registry — add new tools here without touching the streaming logic.
_EXECUTORS: dict[str, callable] = {
    "list_jobs": _exec_list_jobs,
    "get_job_info": _exec_get_job_info,
    "get_job_metrics": _exec_get_job_metrics,
    "get_spatial_summary": _exec_get_spatial_summary,
    "run_code_sandbox": _exec_run_code_sandbox,
    "run_code": _exec_run_code,
}


async def _prepare_tool_result(raw_result: object, session_id: str, user_id: str) -> ToolExecutionResult:
    if isinstance(raw_result, str):
        try:
            parsed = json.loads(raw_result)
        except json.JSONDecodeError:
            parsed = {"raw": raw_result}
        return ToolExecutionResult(content=raw_result, parsed=parsed)

    if not isinstance(raw_result, dict):
        content = json.dumps({"value": raw_result})
        return ToolExecutionResult(content=content, parsed={"value": raw_result})

    parsed = dict(raw_result)
    saved_artifacts = []
    sanitized_artifacts = []
    for artifact_meta in raw_result.get("artifacts", []):
        if not isinstance(artifact_meta, dict):
            continue
        data = artifact_meta.get("data")
        if artifact_meta.get("kind") == "figure" and isinstance(data, (bytes, bytearray)):
            artifact = await create_chat_figure_artifact(
                session_id,
                user_id,
                bytes(data),
                label=artifact_meta.get("label"),
                filename=artifact_meta.get("filename"),
                media_type=artifact_meta.get("media_type"),
            )
            saved_artifacts.append(artifact)
            sanitized_artifacts.append({
                "id": artifact.id,
                "kind": artifact.kind,
                "url": artifact.url,
                "label": artifact.label,
                "media_type": artifact.media_type,
                "filename": artifact.filename,
                "created_at": artifact.created_at.isoformat(),
            })

    payload = {
        key: value
        for key, value in parsed.items()
        if key != "artifacts"
    }
    if sanitized_artifacts:
        payload["artifacts"] = sanitized_artifacts
    content = json.dumps(payload)
    return ToolExecutionResult(content=content, parsed=payload, artifacts=saved_artifacts)


async def execute_tool(name: str, args: dict, user_id: str, scope: ChatScope, session_id: str) -> ToolExecutionResult:
    executor = _EXECUTORS.get(name)
    if not executor:
        return ToolExecutionResult(content=json.dumps({"error": f"Unknown tool: {name}"}), parsed={"error": f"Unknown tool: {name}"})
    try:
        raw_result = await executor(args, user_id, scope)
        return await _prepare_tool_result(raw_result, session_id, user_id)
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return ToolExecutionResult(content=json.dumps({"error": str(exc)}), parsed={"error": str(exc)})


# ---------------------------------------------------------------------------
# Streaming chat completion with tool use
# ---------------------------------------------------------------------------

def get_client():
    from openai import AsyncOpenAI
    from ..config import settings
    if not settings.llm_base_url:
        raise RuntimeError("LLM_BASE_URL is not configured")
    return AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


async def stream_response(
    messages: list[dict],
    user_id: str,
    session_id: str,
    session_scope: ChatScope,
) -> AsyncIterator[str]:
    """
    Run one turn of the conversation, yielding SSE-formatted data lines.

    Handles tool calls automatically: executes them and continues streaming
    until the model produces a final text response.

    Yields JSON strings (without the 'data: ' prefix — the router adds that).
    """
    from ..config import settings

    client = get_client()
    working_messages = list(messages)
    turn = ChatTurn(id=new_turn_id(), role="assistant", content="", created_at=utc_now())

    while True:
        # Accumulate the full response so we can handle tool calls.
        response_message: dict = {"role": "assistant", "content": ""}
        tool_calls: list[dict] = []
        current_tool: dict | None = None

        stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=working_messages,
            tools=TOOLS,
            tool_choice="auto",
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            # Text content
            if delta.content:
                response_message["content"] += delta.content
                turn.content += delta.content
                yield json.dumps({"type": "text_delta", "turn_id": turn.id, "content": delta.content})

            # Tool call deltas — accumulate across chunks
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    if tc_delta.index is not None:
                        # New tool call starting
                        while len(tool_calls) <= tc_delta.index:
                            tool_calls.append({
                                "id": "", "type": "function",
                                "function": {"name": "", "arguments": ""},
                            })
                        current_tool = tool_calls[tc_delta.index]

                    if tc_delta.id:
                        current_tool["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            current_tool["function"]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            current_tool["function"]["arguments"] += tc_delta.function.arguments

        # If no tool calls, we're done — append the final assistant message and emit
        if not tool_calls:
            turn.content = _SANDBOX_IMAGE_RE.sub("", turn.content).strip()
            working_messages.append(response_message)
            yield json.dumps({
                "type": "done",
                "provider_state": working_messages,
                "turn": turn.model_dump(mode="json"),
            })
            return

        # Append the assistant message with tool calls
        response_message["tool_calls"] = tool_calls
        working_messages.append(response_message)

        # Execute each tool and append results
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}

            turn_tool = ChatToolCall(id=tc["id"], name=name, status="running", input=args)
            turn.tool_calls.append(turn_tool)
            yield json.dumps({
                "type": "tool_call",
                "turn_id": turn.id,
                "tool_call": turn_tool.model_dump(mode="json"),
            })
            result = await execute_tool(name, args, user_id, session_scope, session_id)

            for artifact in result.artifacts:
                turn_tool.artifacts.append(artifact)
                turn.artifacts.append(artifact)
                yield json.dumps({
                    "type": "artifact",
                    "turn_id": turn.id,
                    "tool_call_id": turn_tool.id,
                    "artifact": artifact.model_dump(mode="json"),
                })

            parsed_result = result.parsed
            turn_tool.status = "failed" if isinstance(parsed_result, dict) and parsed_result.get("error") else "completed"
            turn_tool.result = parsed_result
            yield json.dumps({
                "type": "tool_result",
                "turn_id": turn.id,
                "tool_call_id": turn_tool.id,
                "status": turn_tool.status,
                "result": parsed_result,
            })

            working_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result.content,
            })
