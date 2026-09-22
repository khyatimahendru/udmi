"""API route handlers for the UDMI Workbench gateway (Layer 4).

Each handler serves real repository data or drives a real process. There are no
placeholder devices, tests, scores, or statuses anywhere in this module.
"""

import json
import time
from typing import Any
from urllib.parse import parse_qs

from workbench.server import (
    artifacts,
    compliance,
    discovery,
    results_commit,
    sequences,
    streams,
)
from workbench.server.artifacts import SandboxError
from workbench.server.compliance import ComplianceError
from workbench.server.discovery import DiscoveryError
from workbench.server.http_util import HttpResponder, read_json_body, require, single
from workbench.server.logger import SERVER_LOGGER
from workbench.server.results_commit import CommitError
from workbench.server.runner import (
    FEATURE_STAGE_ORDER,
    STAGE_LABELS,
    VALID_LOG_LEVELS,
    VALID_STAGES,
    RunnerError,
    stages_admitted,
)
from workbench.server.site_roots import SiteRootError
from workbench.server.testbed import TestbedError


class ApiRoutes:
    """Binds HTTP requests to discovery, runner, and MCP operations."""

    def __init__(self, context: Any):
        self.ctx = context

    def _site_roots(self) -> list:
        """The directories outside the checkout the operator has consented to."""
        return self.ctx.site_roots.paths()

    # ---------------------------------------------------------------- GET ---
    def handle_get(self, path: str, query: str, responder: HttpResponder) -> bool:
        """Dispatches a GET request. Returns False if the path is not an API route."""
        params = parse_qs(query)
        root = self.ctx.udmi_root

        if path == "/api/health":
            responder.json({
                "status": "OK",
                "service": "udmi-workbench",
                "udmi_root": root,
                "mcp_tools": len(self.ctx.mcp_tool_names()),
            })
        elif path == "/api/site-models":
            responder.json(discovery.list_site_models(root, self._site_roots()))
        elif path == "/api/site-roots":
            responder.json(self.ctx.site_roots.describe())
        elif path == "/api/devices":
            site_model = require(params, "site_model")
            responder.json({
                "site_model": site_model,
                "devices": discovery.list_devices(root, site_model),
            })
        elif path == "/api/device":
            site_model = require(params, "site_model")
            device_id = require(params, "device_id")
            responder.json({
                "site_model": site_model,
                "device_id": device_id,
                "metadata": discovery.get_device_metadata(root, site_model, device_id),
            })
        elif path == "/api/sequences":
            responder.json({"sequences": sequences.list_sequences(root)})
        elif path == "/api/results":
            site_model = require(params, "site_model")
            device_id = require(params, "device_id")
            responder.json(discovery.get_device_results(root, site_model, device_id))
        elif path == "/api/browse":
            responder.json(
                artifacts.browse(root, single(params, "path", "") or "", self._site_roots())
            )
        elif path == "/api/file":
            responder.json(
                artifacts.read_text(root, require(params, "path"), self._site_roots())
            )
        elif path == "/api/sequencer/options":
            responder.json(self._run_options())
        elif path == "/api/sequencer/sessions":
            responder.json({"sessions": self.ctx.runner.list_sessions()})
        elif path == "/api/sequencer/stream":
            streams.stream_sequencer(self.ctx, params, responder)
        elif path == "/api/compliance":
            responder.json(compliance.site_compliance(root, require(params, "site_model")))
        elif path == "/api/device/report":
            report = compliance.device_report(
                root,
                require(params, "site_model"),
                require(params, "device_id"),
                require(params, "kind"),
            )
            responder.attachment(
                report["content"], report["filename"], report["content_type"]
            )
        elif path == "/api/results/commit/preview":
            site_model = require(params, "site_model")
            device_id = require(params, "device_id")
            responder.json(results_commit.preview(root, site_model, device_id))
        elif path == "/api/diagnostics/logs":
            limit = int(single(params, "limit", "200") or 200)
            entries = SERVER_LOGGER.get_entries(limit=limit)
            responder.json({"entries": entries, "count": len(entries)})
        elif path == "/api/testbed/status":
            responder.json(self.ctx.testbed.get_status())
        elif path == "/api/testbed/logs":
            component = single(params, "component", "setup") or "setup"
            tail = int(single(params, "tail", "100") or 100)
            responder.json(self.ctx.testbed.get_logs(component, tail=tail))
        else:
            return False
        return True

    # --------------------------------------------------------------- POST ---
    def handle_post(self, path: str, responder: HttpResponder) -> bool:
        """Dispatches a POST request. Returns False if the path is not an API route."""
        if path in ("/rpc", "/message"):
            self._handle_rpc(responder)
        elif path == "/api/site-roots":
            body = read_json_body(responder.handler)
            responder.json(
                self.ctx.site_roots.register(
                    body.get("path"), correlation_id=responder.correlation_id
                )
            )
        elif path == "/api/testbed/start":
            body = read_json_body(responder.handler)
            responder.json(
                self.ctx.testbed.start(
                    site_model=body.get("site_model"),
                    project_spec=body.get("project_spec"),
                    clean=bool(body.get("clean", False)),
                    correlation_id=responder.correlation_id,
                )
            )
        elif path == "/api/testbed/stop":
            responder.json(self.ctx.testbed.stop(correlation_id=responder.correlation_id))
        elif path == "/api/testbed/restart":
            body = read_json_body(responder.handler)
            responder.json(
                self.ctx.testbed.restart(
                    site_model=body.get("site_model"),
                    project_spec=body.get("project_spec"),
                    correlation_id=responder.correlation_id,
                )
            )
        elif path == "/api/testbed/pubber/start":
            body = read_json_body(responder.handler)
            responder.json(
                self.ctx.testbed.start_pubber(
                    site_model=body.get("site_model"),
                    device_id=body.get("device_id"),
                    project_spec=body.get("project_spec"),
                    serial_no=body.get("serial_no") or "1234",
                    correlation_id=responder.correlation_id,
                )
            )
        elif path == "/api/testbed/pubber/stop":
            body = read_json_body(responder.handler)
            responder.json(
                self.ctx.testbed.stop_pubber(
                    device_id=body.get("device_id"),
                    correlation_id=responder.correlation_id,
                )
            )
        elif path == "/api/sequencer/run":
            self._start_sequencer(responder)
        elif path == "/api/sequencer/stop":
            body = read_json_body(responder.handler)
            session_id = body.get("session_id")
            if not session_id:
                raise ValueError("Missing required field: 'session_id'")
            responder.json(self.ctx.runner.stop(session_id, correlation_id=responder.correlation_id))
        elif path == "/api/results/commit":
            self._commit_results(responder)
        elif path == "/api/mantis/chat":
            streams.stream_mantis(self.ctx, responder)
        elif path == "/api/mantis/chat/clear":
            body = read_json_body(responder.handler)
            session_id = body.get("session_id") or "workbench-assistant"
            responder.json(self.ctx.mantis_store.clear_session(session_id))
        else:
            return False
        return True

    # ------------------------------------------------------------- DELETE ---
    def handle_delete(self, path: str, query: str, responder: HttpResponder) -> bool:
        """Dispatches a DELETE request. Returns False if the path is not an API route."""
        if path == "/api/site-roots":
            target = require(parse_qs(query), "path")
            responder.json(
                self.ctx.site_roots.unregister(target, correlation_id=responder.correlation_id)
            )
        else:
            return False
        return True

    # ------------------------------------------------------------ handlers ---
    def _run_options(self) -> dict:
        """Backend-owned whitelists for every `bin/sequencer` option."""
        return {
            "log_levels": [
                {"value": name, "flags": flags}
                for name, flags in VALID_LOG_LEVELS.items()
            ],
            "min_stages": [
                {
                    "value": name,
                    "flags": flags,
                    "label": STAGE_LABELS[name],
                    "admits": stages_admitted(name),
                }
                for name, flags in VALID_STAGES.items()
            ],
            "feature_stage_order": list(FEATURE_STAGE_ORDER),
        }

    def _handle_rpc(self, responder: HttpResponder) -> None:
        """Contract 1: MCP JSON-RPC 2.0 passthrough to the Mantis tool registry."""
        body = read_json_body(responder.handler)
        tool_name = (body.get("params") or {}).get("name")
        started = time.time()
        SERVER_LOGGER.info(
            "McpGateway",
            "rpc.call.start",
            correlation_id=responder.correlation_id,
            layer="MCP_RPC",
            context={"toolName": tool_name},
            details={"method": body.get("method")},
        )
        result = self.ctx.mcp_server.handle_request(body)
        SERVER_LOGGER.info(
            "McpGateway",
            "rpc.call.complete",
            correlation_id=responder.correlation_id,
            layer="MCP_RPC",
            duration_ms=(time.time() - started) * 1000,
            context={"toolName": tool_name},
        )
        responder.json(result or {})

    def _start_sequencer(self, responder: HttpResponder) -> None:
        """Launches a real `bin/sequencer` run from explicit user-supplied inputs."""
        body = read_json_body(responder.handler)
        site_model = body.get("site_model")
        if not site_model:
            raise ValueError("Missing required field: 'site_model'")
        device_id = body.get("device_id")
        if not device_id:
            raise ValueError("Missing required field: 'device_id'")
        project_spec = body.get("project_spec")
        if not project_spec:
            raise ValueError("Missing required field: 'project_spec'")

        tests = body.get("tests") or []
        if not isinstance(tests, list):
            raise ValueError("Field 'tests' must be a list of sequence names")

        min_stage = body.get("min_stage") or "PREVIEW"
        sequences.reject_stage_excluded(self.ctx.udmi_root, tests, min_stage)

        site_model_abs = discovery.resolve_site_model(self.ctx.udmi_root, site_model)
        started = self.ctx.runner.start(
            site_model_abs=site_model_abs,
            project_spec=project_spec,
            device_id=device_id,
            tests=tests,
            log_level=body.get("log_level") or "INFO",
            min_stage=min_stage,
            serial_no=body.get("serial_no"),
            correlation_id=responder.correlation_id,
        )
        started["site_model"] = site_model
        started["stages_admitted"] = stages_admitted(min_stage)
        responder.json(started)

    def _commit_results(self, responder: HttpResponder) -> None:
        """Commits one device's recorded results. Always user-initiated.

        Every option is taken verbatim from the request. The handler deliberately
        supplies no defaults for `branch` or `remote`: picking one here would mean
        guessing which branch a lab's results belong on, and `results_commit`
        rejects an underspecified push rather than inventing a target.
        """
        body = read_json_body(responder.handler)
        responder.json(
            results_commit.commit(
                self.ctx.udmi_root,
                body.get("site_model"),
                body.get("device_id"),
                message=body.get("message"),
                branch=body.get("branch"),
                create_branch=bool(body.get("create_branch", False)),
                push=bool(body.get("push", False)),
                remote=body.get("remote"),
                summary=body.get("summary"),
                project_spec=body.get("project_spec"),
                correlation_id=responder.correlation_id,
            )
        )


def classify_exception(exc: Exception) -> int:
    """Maps a domain exception to an HTTP status code."""
    if isinstance(exc, (DiscoveryError, SandboxError)):
        return 404 if "not found" in str(exc).lower() else 403
    if isinstance(exc, ComplianceError):
        return 404 if "not found" in str(exc).lower() else 400
    if isinstance(exc, (ValueError, RunnerError, CommitError, SiteRootError,
                        TestbedError, json.JSONDecodeError)):
        return 400
    return 500
