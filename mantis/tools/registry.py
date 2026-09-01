"""Centralized Tool Registry, Schemas, and Unified Execution Dispatcher for Mantis and MCP."""

from dataclasses import dataclass
import inspect
from typing import Any, Callable, Dict, List, Optional, Type
from pydantic import BaseModel

from mcp.session_manager import SessionManager
from mantis.models import (
    DiagnoseFailureRequest,
    DifferentialRequest,
    EnsureSetupRequest,
    GetLogsRequest,
    PatchSiteModelRequest,
    PublishMqttRequest,
    QueryDatabaseRequest,
    RunSequencerTestRequest,
    SchemaInspectRequest,
    SiteModelInspectRequest,
    StabilityEvaluationRequest,
    StartProcessRequest,
    TerminateSetupRequest,
    TimelineRequest,
)
from mantis.tools.artifacts import extract_timeline
from mantis.tools.diagnostics import diagnose_test_failure, evaluate_test_stability
from mantis.tools.differential import compare_test_runs
from mantis.tools.patcher import patch_site_model
from mantis.tools.schemas import inspect_udmi_schema
from mantis.tools.site_models import inspect_site_model


@dataclass
class ToolDefinition:
    name: str
    description: str
    func: Callable[..., Any]
    request_model: Optional[Type[BaseModel]] = None
    manual_schema: Optional[Dict[str, Any]] = None


_REGISTERED_TOOLS: Dict[str, ToolDefinition] = {}


def register_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    request_model: Optional[Type[BaseModel]] = None,
    manual_schema: Optional[Dict[str, Any]] = None,
):
    """Decorator to register a tool function with automatic Pydantic validation and schema exposure."""
    def decorator(fn: Callable[..., Any]):
        tool_name = name or fn.__name__
        tool_desc = description or (fn.__doc__ or "").strip()
        _REGISTERED_TOOLS[tool_name] = ToolDefinition(
            name=tool_name,
            description=tool_desc,
            func=fn,
            request_model=request_model,
            manual_schema=manual_schema,
        )
        return fn
    return decorator


# ------------------------------------------------------------------------------
# Tool Registrations (Tier 1 - Tier 4)
# ------------------------------------------------------------------------------

# Tier 1: Session & Process Lifecycle
@register_tool(
    name="ensure_test_setup",
    description="Ensures that an isolated local UDMI test infrastructure stack (Mosquitto broker, UDMIS control plane, etcd, InfluxDB, PostgreSQL, and optional DUT) is running inside a tmux session, healthy, and ready for client traffic.",
    request_model=EnsureSetupRequest,
)
def _tool_ensure_test_setup(session_mgr: SessionManager, **kwargs):
    return session_mgr.ensure_test_setup(**kwargs)


@register_tool(
    name="run_sequencer_test",
    description="Launches a sequencer test sequence (e.g. 'pointset_publish', 'system_last_update') against a local broker or remote cloud endpoint (e.g. '//gbos/bos-platform-dev/faucetsdn', '//gcp/project/registry', '//mqtt/localhost:28430'). Does not require local Docker/infrastructure setup for cloud endpoints.",
    request_model=RunSequencerTestRequest,
)
def _tool_run_sequencer_test(
    session_mgr: SessionManager,
    test_name: str,
    device_id: str = "AHU-1",
    target_spec: Optional[str] = None,
    site_model: str = "sites/udmi_site_model",
    session_id: Optional[str] = None,
):
    return session_mgr.run_sequencer_test(
        test_name=test_name,
        device_id=device_id,
        target_spec=target_spec,
        site_model=site_model,
        session_id=session_id,
    )


@register_tool(
    name="start_session_process",
    description="Launches a command or test process inside a named semantic window of an active UDMI session (e.g. launching sequencer tests, custom Pubber devices, or monitoring scripts).",
    request_model=StartProcessRequest,
)
def _tool_start_session_process(session_mgr: SessionManager, test_id: str, window: str, command: str):
    return session_mgr.start_session_process(test_id=test_id, window=window, command=command)


@register_tool(
    name="terminate_test_setup",
    description="Terminates an active UDMI isolated tmux session and optionally cleans instance files.",
    request_model=TerminateSetupRequest,
)
def _tool_terminate_test_setup(session_mgr: SessionManager, test_id: str, clean_workspace: bool = True):
    return session_mgr.terminate_test_setup(test_id=test_id, clean_workspace=clean_workspace)


@register_tool(
    name="list_test_setups",
    description="Lists all currently active isolated UDMI test infrastructure sessions.",
)
def _tool_list_test_setups(session_mgr: SessionManager):
    return session_mgr.list_test_setups()


@register_tool(
    name="list_test_windows",
    description="Lists all active named semantic windows (e.g. main, dut, sequencer, butler, validator) within a test session.",
    manual_schema={
        "type": "object",
        "required": ["test_id"],
        "properties": {
            "test_id": {"type": "string", "description": "Identifier of the active test session."}
        },
    },
)
def _tool_list_test_windows(session_mgr: SessionManager, test_id: str):
    if not test_id:
        raise ValueError("Parameter 'test_id' is required for list_test_windows")
    return session_mgr.list_test_windows(test_id=test_id)


@register_tool(
    name="get_test_logs",
    description="Captures live console output from a named semantic tmux window (e.g. 'main', 'dut', 'sequencer', 'butler', 'validator') for an active test session.",
    request_model=GetLogsRequest,
)
def _tool_get_test_logs(session_mgr: SessionManager, test_id: str, window: str = "main", lines: int = 100):
    return session_mgr.get_test_logs(test_id=test_id, window=window, lines=lines)


# Tier 2: Real-time Inspection & Mutation
@register_tool(
    name="query_database",
    description="Executes a read-only SQL or Flux query against the isolated PostgreSQL or InfluxDB database instance.",
    request_model=QueryDatabaseRequest,
)
def _tool_query_database(session_mgr: SessionManager, test_id: str, database_type: Any, query: str):
    db_type_val = database_type.value if hasattr(database_type, "value") else str(database_type)
    return session_mgr.query_database(test_id=test_id, database_type=db_type_val, query=query)


@register_tool(
    name="publish_mqtt_message",
    description="Publishes a raw payload directly to an MQTT topic on the isolated local Mosquitto broker.",
    request_model=PublishMqttRequest,
)
def _tool_publish_mqtt_message(session_mgr: SessionManager, test_id: str, topic: str, payload: str):
    return session_mgr.publish_mqtt_message(test_id=test_id, topic=topic, payload=payload)


# Tier 3: Specification & Site Model Grounding
@register_tool(
    name="inspect_udmi_schema",
    description="Resolves and inspects official UDMI JSON schemas under schema/.",
    request_model=SchemaInspectRequest,
)
def _tool_inspect_udmi_schema(schema_name: str, sub_path: Optional[str] = None, udmi_root: Optional[str] = None):
    return inspect_udmi_schema(schema_name=schema_name, sub_path=sub_path, udmi_root=udmi_root)


@register_tool(
    name="inspect_site_model",
    description="Inspects and validates site model directories and device metadata definitions.",
    request_model=SiteModelInspectRequest,
)
def _tool_inspect_site_model(site_model: str = "sites/udmi_site_model", device_id: Optional[str] = None, udmi_root: Optional[str] = None):
    return inspect_site_model(site_model=site_model, device_id=device_id, udmi_root=udmi_root)


@register_tool(
    name="patch_site_model",
    description="Safely mutates device metadata.json with atomic backup and unified diff preview.",
    request_model=PatchSiteModelRequest,
)
def _tool_patch_site_model(site_model: str, device_id: str, patch_data: Dict[str, Any], dry_run: bool = False, udmi_root: Optional[str] = None):
    return patch_site_model(site_model=site_model, device_id=device_id, patch_data=patch_data, dry_run=dry_run, udmi_root=udmi_root)


# Tier 4: Diagnostic Intelligence
@register_tool(
    name="get_test_timeline",
    description="Extracts chronological timestamps, transaction IDs (RC:...), cutoffs, and status transitions from test logs.",
    request_model=TimelineRequest,
)
def _tool_get_test_timeline(test_id: str, device_id: str, run_dir: Optional[str] = None, udmi_root: Optional[str] = None):
    return extract_timeline(test_id=test_id, device_id=device_id, run_dir=run_dir, udmi_root=udmi_root)


@register_tool(
    name="compare_test_runs",
    description="Performs behavioral differential sequence alignment between a target test run and a reference baseline.",
    request_model=DifferentialRequest,
)
def _tool_compare_test_runs(target_run: str, baseline_run: Optional[str] = None, udmi_root: Optional[str] = None):
    return compare_test_runs(target_run=target_run, baseline_run=baseline_run, udmi_root=udmi_root)


@register_tool(
    name="diagnose_test_failure",
    description="Performs complete root-cause analysis on a failed test execution using the built-in adversarial critique loop.",
    request_model=DiagnoseFailureRequest,
)
def _tool_diagnose_test_failure(test_id: str, device_id: str, site_model: str = "sites/udmi_site_model", run_dir: Optional[str] = None, udmi_root: Optional[str] = None):
    return diagnose_test_failure(test_id=test_id, device_id=device_id, site_model=site_model, run_dir=run_dir, udmi_root=udmi_root)


@register_tool(
    name="evaluate_test_stability",
    description="Calculates empirical reliability score, flakiness index, and failure mode distribution across test runs.",
    request_model=StabilityEvaluationRequest,
)
def _tool_evaluate_test_stability(test_id: Optional[str] = None, site_model: str = "sites/udmi_site_model", base_dir: Optional[str] = None, udmi_root: Optional[str] = None):
    return evaluate_test_stability(test_id=test_id, site_model=site_model, base_dir=base_dir, udmi_root=udmi_root)


# ------------------------------------------------------------------------------
# Dispatch & Schema Inspection
# ------------------------------------------------------------------------------

def execute_tool(
    name: str,
    args: Dict[str, Any],
    session_mgr: Optional[SessionManager] = None,
    udmi_root: Optional[str] = None,
) -> Any:
    """Executes a registered tool with automatic Pydantic validation and dependency injection."""
    if name not in _REGISTERED_TOOLS:
        raise ValueError(f"Unknown tool: '{name}'")

    tool_def = _REGISTERED_TOOLS[name]
    func = tool_def.func

    if tool_def.request_model:
        validated = tool_def.request_model(**args)
        call_kwargs = validated.model_dump()
    else:
        call_kwargs = dict(args)

    sig = inspect.signature(func)
    if "session_mgr" in sig.parameters:
        call_kwargs["session_mgr"] = session_mgr or SessionManager(udmi_root=udmi_root)
    if "udmi_root" in sig.parameters:
        call_kwargs["udmi_root"] = udmi_root

    filtered_kwargs = {}
    for param_name, param in sig.parameters.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            filtered_kwargs = call_kwargs
            break
        if param_name in call_kwargs:
            filtered_kwargs[param_name] = call_kwargs[param_name]

    return func(**filtered_kwargs)


def _clean_json_schema(raw_schema: Dict[str, Any]) -> Dict[str, Any]:
    """Inlines $defs and removes Pydantic-internal fields to ensure compatibility with GenAI and MCP."""
    import copy
    schema = copy.deepcopy(raw_schema)
    defs = schema.pop("$defs", {})
    schema.pop("title", None)

    def _resolve_refs(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_key = node["$ref"].split("/")[-1]
                if ref_key in defs:
                    resolved = copy.deepcopy(defs[ref_key])
                    resolved.pop("title", None)
                    return _resolve_refs(resolved)
            return {k: _resolve_refs(v) for k, v in node.items() if k != "title"}
        elif isinstance(node, list):
            return [_resolve_refs(item) for item in node]
        return node

    return _resolve_refs(schema)


def get_mcp_tools() -> List[Dict[str, Any]]:
    """Returns all registered tool schemas formatted for MCP tools/list."""
    tools = []
    for name, tool_def in _REGISTERED_TOOLS.items():
        if tool_def.manual_schema:
            schema = _clean_json_schema(tool_def.manual_schema)
        elif tool_def.request_model:
            schema = _clean_json_schema(tool_def.request_model.model_json_schema())
        else:
            schema = {"type": "object", "properties": {}}

        tools.append({
            "name": name,
            "description": tool_def.description,
            "inputSchema": schema,
        })
    return tools


def get_tool_schemas() -> List[Dict[str, Any]]:
    """Returns tool schemas formatted for standard function declarations."""
    schemas = []
    for name, tool_def in _REGISTERED_TOOLS.items():
        if tool_def.manual_schema:
            params = _clean_json_schema(tool_def.manual_schema)
        elif tool_def.request_model:
            params = _clean_json_schema(tool_def.request_model.model_json_schema())
        else:
            params = {"type": "object", "properties": {}}

        schemas.append({
            "name": name,
            "description": tool_def.description,
            "parameters": params,
        })
    return schemas


def get_genai_tools() -> List[Any]:
    """Generates google.genai.types.Tool containing all FunctionDeclarations."""
    try:
        from google.genai import types
        function_declarations = []
        for schema in get_tool_schemas():
            fd = types.FunctionDeclaration(
                name=schema["name"],
                description=schema["description"],
                parameters=schema["parameters"],
            )
            function_declarations.append(fd)
        return [types.Tool(function_declarations=function_declarations)]
    except Exception:
        return []


TOOL_SCHEMAS = get_tool_schemas()
