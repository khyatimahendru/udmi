"""Contract 2: Mantis streaming agent adapter (Layer 4).

Bridges the Mantis reasoning agent to Server-Sent Events. Every phase, tool call,
hypothesis, and token emitted here originates from a real agent run against a real
model. When the agent cannot run, this adapter emits an explicit `error` event
rather than inventing findings.

A note on what this module deliberately does NOT do. An earlier version answered
triage requests by calling `mantis.tools.diagnostics.diagnose_test_failure` and
streaming its output as the reply. That tool is deterministic and evaluates a fixed
catalogue of nine known failure modes, emitting a verdict for every one of them on
every run. The result looked like an analysis but was a checklist: it returned in
milliseconds, always produced the same nine rows regardless of the failure, and its
templated prose frequently rendered unfilled placeholders. Triage now runs the real
agent, and that tool is offered to it as one evidence source among many.
"""

from datetime import datetime, timezone
import json
import os
import queue
import re
import threading
import time
from typing import Any, Dict, Generator, List, Optional

from mantis.config import CONFIG, ProviderType
from mantis.models import ChatMessage, MessageRole, SessionContext
from mantis.session import SessionManager
from mantis.tools.registry import get_mcp_tools
from workbench.server.logger import SERVER_LOGGER

TRIAGE_KEYWORDS = ("fail", "triage", "root cause", "why did", "diagnose", "debug")
AGENT_TIMEOUT_SECONDS = 600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MantisSessionStore:
    """Tracks conversational sessions and streams agent activity as SSE events."""

    def __init__(self, session_mgr: SessionManager):
        self.session_mgr = session_mgr
        self._sessions: Dict[str, SessionContext] = {}
        self._cancelled: Dict[str, bool] = {}

    # ------------------------------------------------------------ sessions ---
    def get_or_create(self, session_id: str, overrides: Optional[Dict[str, Any]] = None) -> SessionContext:
        context = self._sessions.setdefault(session_id, SessionContext(active_session_id=session_id))
        if overrides:
            if overrides.get("site_model"):
                context.active_site_model = overrides["site_model"]
            if overrides.get("device_id"):
                context.active_device_id = overrides["device_id"]
            if overrides.get("test_id"):
                context.active_test_id = overrides["test_id"]
        return context

    def stop_session(self, session_id: str) -> Dict[str, Any]:
        self._cancelled[session_id] = True
        return {"session_id": session_id, "status": "STOPPED"}

    def clear_session(self, session_id: str) -> Dict[str, Any]:
        self.get_or_create(session_id).history.clear()
        self._cancelled[session_id] = False
        return {"session_id": session_id, "status": "CLEARED"}

    def get_status(self, session_id: str) -> Dict[str, Any]:
        context = self.get_or_create(session_id)
        return {
            "session_id": session_id,
            "site_model": context.active_site_model,
            "device_id": context.active_device_id,
            "test_id": context.active_test_id,
            "turns": len(context.history),
            "tools_available": len(get_mcp_tools()),
        }

    # -------------------------------------------------------------- stream ---
    def stream_chat_events(
        self, payload: Dict[str, Any], correlation_id: str
    ) -> Generator[Dict[str, Any], None, None]:
        """Yields Contract 2 SSE events for one chat or triage request."""
        session_id = payload.get("session_id") or "sess-default"
        message = (payload.get("message") or "").strip()
        if not message:
            yield {"event": "error", "data": {"message": "Field 'message' must not be empty."}}
            return

        context = self.get_or_create(session_id, payload.get("context") or {})

        # Extract test_id from message if not explicitly supplied in context
        if not context.active_test_id:
            quoted = re.search(r"['\"]([a-zA-Z0-9_+]+(?:_[a-zA-Z0-9_+]+)+)['\"]", message)
            if quoted:
                context.active_test_id = quoted.group(1)
            else:
                test_match = re.search(
                    r"\b(?:test|sequence)\s+['\"]?([a-zA-Z0-9_+]+)['\"]?",
                    message,
                    re.IGNORECASE,
                )
                if test_match:
                    context.active_test_id = test_match.group(1)
                else:
                    for word in re.findall(r"\b[a-z]+(?:_[a-z0-9]+)+\b", message):
                        if not any(
                            word.startswith(p)
                            for p in ("how_", "why_", "what_", "when_", "where_", "can_")
                        ):
                            context.active_test_id = word
                            break

        # Extract device_id from message if not in context
        if not context.active_device_id:
            dev_match = re.search(
                r"\b(?:device|dut)\s+['\"]?([A-Za-z0-9_-]+)['\"]?", message, re.IGNORECASE
            )
            if dev_match:
                context.active_device_id = dev_match.group(1)

        # Default site model if not set
        if not context.active_site_model:
            site_match = re.search(r"(sites/[a-zA-Z0-9_\-\./]+)", message)
            if site_match:
                context.active_site_model = site_match.group(1)
            else:
                context.active_site_model = "sites/udmi_site_model"

        context.history.append(
            ChatMessage(role=MessageRole.USER, content=message, timestamp=_now())
        )
        self._cancelled[session_id] = False

        SERVER_LOGGER.info(
            "MantisStreamAdapter",
            "sse.connect",
            correlation_id=correlation_id,
            layer="MANTIS_SSE",
            context={
                "sessionId": session_id,
                "deviceId": context.active_device_id,
                "testId": context.active_test_id,
            },
        )

        if message.startswith("/"):
            yield from self._slash_command(session_id, message, context)
            return

        # Mantis is a reasoning agent. Without a model provider there is no analysis
        # to give, and emitting a canned report in its place is what made the previous
        # implementation untrustworthy: it looked like a diagnosis and was not one.
        if CONFIG.provider == ProviderType.OFFLINE_DETERMINISTIC:
            yield {
                "event": "error",
                "data": {
                    "message": (
                        "Mantis has no model provider configured, so it cannot analyse this "
                        "failure. MANTIS_OFFLINE is set, which disables the reasoning engine. "
                        "Unset MANTIS_OFFLINE and provide either GEMINI_API_KEY (AI Studio) or "
                        "Google Cloud application-default credentials (Vertex AI), then retry."
                    )
                },
            }
            return

        started = time.time()
        if self._is_triage(message, context):
            prompt = self._triage_prompt(context)
            if prompt is None:
                yield {
                    "event": "error",
                    "data": {
                        "message": (
                            "Triage requires both a device and a test. "
                            "Select a failed test first, or ask a general question instead."
                        )
                    },
                }
                return
        else:
            prompt = message

        run_metrics: Dict[str, Any] = {}
        yield from self._run_agent(
            prompt=prompt,
            context=context,
            session_id=session_id,
            correlation_id=correlation_id,
            metrics_sink=run_metrics,
        )

        run_metrics["total_duration_sec"] = round(time.time() - started, 2)
        yield {
            "event": "done",
            "data": {"session_id": session_id, "metrics": run_metrics},
        }

    @staticmethod
    def _is_triage(message: str, context: SessionContext) -> bool:
        lowered = message.lower().strip()
        if any(lowered.startswith(p) for p in ("/diagnose", "/triage", "diagnose", "triage", "run triage")):
            return True
        if re.search(r"\b(?:why did|how did)\b.*?\bfail\b", lowered) and re.search(r"\b(?:test|sequence)\b", lowered):
            return True
        return False

    def _triage_prompt(self, context: SessionContext) -> Optional[str]:
        """Builds the triage instruction, or None when there is nothing to triage.

        The deterministic `diagnose_test_failure` tool is named here as the agent's
        FIRST step rather than used as the answer. That tool harvests a timeline and
        checks a fixed catalogue of known failure modes, which is genuinely useful
        evidence; what it cannot do is decide which of its findings explains THIS
        failure, because it emits a verdict for every hypothesis it knows about
        whether or not that hypothesis is relevant. Handing its output to the agent
        as evidence, and requiring the agent to verify it against the actual logs,
        is the difference between a checklist and a diagnosis.
        """
        device_id = context.active_device_id
        test_id = context.active_test_id
        if not device_id or not test_id:
            return None

        site_model = context.active_site_model
        lines = [
            f"Diagnose why sequencer test '{test_id}' failed for device '{device_id}' "
            f"in site model '{site_model}'.",
            "",
            "Investigation requirements:",
            f"1. Call diagnose_test_failure(test_id='{test_id}', device_id='{device_id}', "
            f"site_model='{site_model}') first to harvest the deterministic timeline, "
            "transaction ids, and cutoff thresholds from the recorded run.",
            "2. Treat that tool's output as EVIDENCE, not as a conclusion. It reports a "
            "verdict for every failure mode it knows about, including ones irrelevant to "
            "this run. Verify anything you intend to rely on against the actual sequence "
            "logs and the UDMI source before citing it.",
            "3. Establish which single mechanism accounts for the failure. If the evidence "
            "cannot settle it, say so and state what would.",
        ]

        run_dir = self._run_dir(context)
        if run_dir:
            lines.append(f"4. The recorded artifacts for this run are on disk at: {run_dir}")
        else:
            lines.append(
                "4. No recorded artifact directory exists on disk for this test, so there "
                "is no runtime log evidence. Say so explicitly in your answer rather than "
                "presenting source inference as observation."
            )

        lines += [
            "",
            "Write for a lab operator who needs to know what to change. Lead with a one "
            "sentence root cause in plain language, then the evidence that establishes it, "
            "then the concrete fix. Do not pad the answer with refuted possibilities.",
        ]
        return "\n".join(lines)

    def _run_dir(self, context: SessionContext) -> Optional[str]:
        """Locates the recorded artifact directory for the active test, if any."""
        if not (context.active_site_model and context.active_device_id and context.active_test_id):
            return None
        udmi_root = getattr(self.session_mgr, "udmi_root", None) or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        try:
            from workbench.server.discovery import resolve_site_model

            site_dir = resolve_site_model(udmi_root, context.active_site_model)
        except Exception:
            return None
        test_dir = os.path.join(
            site_dir, "out", "devices", context.active_device_id,
            "tests", context.active_test_id,
        )
        return test_dir if os.path.isdir(test_dir) else None

    def _run_agent(
        self,
        prompt: str,
        context: SessionContext,
        session_id: str,
        correlation_id: str,
        metrics_sink: Dict[str, Any],
    ) -> Generator[Dict[str, Any], None, None]:
        """Streams one real MantisAgent run as Contract 2 SSE events.

        Two channels arrive from the agent and are deliberately kept apart. The prose
        channel carries interim reasoning and orchestrator narration; it is surfaced as
        `thought`, which the UI renders in a collapsible disclosure. Only the answer the
        agent finally returns is surfaced as `token`. Mixing the two is what previously
        produced an unreadable reply: ReAct step narration and critic audit text landed
        in the same bubble as the conclusion.
        """
        from mantis.agent import MantisAgent

        events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        SENTINEL = "__final__"

        def on_token(chunk: str) -> None:
            events.put({"kind": "prose", "text": chunk})

        def on_event(record: Dict[str, Any]) -> None:
            events.put({"kind": "record", "record": record})

        def worker() -> None:
            try:
                agent = MantisAgent()
                answer = agent.run(
                    prompt,
                    context=context,
                    stream_callback=on_token,
                    event_callback=on_event,
                )
                events.put({"kind": SENTINEL, "answer": answer or "", "error": None})
            except Exception as exc:
                events.put({
                    "kind": SENTINEL,
                    "answer": "",
                    "error": f"{exc.__class__.__name__}: {exc}",
                })

        threading.Thread(target=worker, daemon=True).start()

        pending_hypotheses: List[str] = []
        deadline = time.time() + AGENT_TIMEOUT_SECONDS

        while time.time() < deadline:
            if self._cancelled.get(session_id):
                yield {"event": "error", "data": {"message": "Cancelled by user."}}
                return
            try:
                item = events.get(timeout=0.5)
            except queue.Empty:
                continue

            kind = item["kind"]

            if kind == "prose":
                yield {"event": "thought", "data": {"text": item["text"]}}
                continue

            if kind == "record":
                for translated in self._translate(item["record"], pending_hypotheses, metrics_sink):
                    yield translated
                continue

            # Sentinel: the run has finished one way or the other.
            if item["error"]:
                SERVER_LOGGER.error(
                    "MantisStreamAdapter",
                    "agent.error",
                    correlation_id=correlation_id,
                    layer="MANTIS_SSE",
                    context={
                        "sessionId": session_id,
                        "deviceId": context.active_device_id,
                        "testId": context.active_test_id,
                    },
                    error={"code": "AGENT", "message": item["error"]},
                )
                yield {"event": "error", "data": {"message": item["error"]}}
                return

            answer = item["answer"]
            if not answer.strip():
                yield {
                    "event": "error",
                    "data": {"message": "Mantis completed without producing an answer."},
                }
                return

            yield {"event": "token", "data": {"text": answer}}
            context.history.append(
                ChatMessage(role=MessageRole.ASSISTANT, content=answer, timestamp=_now())
            )
            return

        yield {
            "event": "error",
            "data": {
                "message": (
                    f"Mantis exceeded the {AGENT_TIMEOUT_SECONDS}s analysis budget and was "
                    "stopped. Narrow the question, or inspect the partial reasoning above."
                )
            },
        }

    def _translate(
        self,
        record: Dict[str, Any],
        pending_hypotheses: List[str],
        metrics_sink: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Maps one agent record onto zero or more Contract 2 SSE events."""
        record_type = record.get("type")

        if record_type == "phase":
            return [{"event": "phase", "data": {"phase": record.get("phase")}}]

        if record_type == "tool_call":
            return [{
                "event": "tool_call",
                "data": {
                    "call_id": record.get("call_id"),
                    "tool": record.get("tool"),
                    "args": record.get("args") or {},
                    "timestamp": _now(),
                },
            }]

        if record_type == "tool_result":
            return [{
                "event": "tool_result",
                "data": {
                    "call_id": record.get("call_id"),
                    "tool": record.get("tool"),
                    "summary": record.get("status") or "completed",
                    "output": record.get("output"),
                },
            }]

        if record_type == "hypotheses":
            # The plan's hypotheses, shown as soon as the agent commits to them so the
            # operator can see what is being investigated while it is still running.
            pending_hypotheses[:] = record.get("hypotheses") or []
            if not pending_hypotheses:
                return []
            return [{
                "event": "hypothesis_matrix",
                "data": {
                    "hypotheses": [
                        {
                            "hypothesis": text,
                            "verdict": "UNRESOLVED",
                            "rationale": "Under investigation.",
                            "evidence_tier": "NONE",
                        }
                        for text in pending_hypotheses
                    ],
                    "final": False,
                },
            }]

        if record_type == "audit":
            rows = record.get("hypotheses") or []
            if not rows:
                return []
            return [{
                "event": "hypothesis_matrix",
                "data": {
                    "hypotheses": [
                        {
                            "hypothesis": row.get("hypothesis"),
                            "verdict": row.get("verdict") or "UNRESOLVED",
                            "rationale": (
                                "" if row.get("verdict")
                                else "The agent returned no verdict for this hypothesis."
                            ),
                            "evidence_tier": "LOCAL_FILE" if row.get("verdict") else "NONE",
                        }
                        for row in rows
                    ],
                    "final": True,
                },
            }]

        if record_type == "metrics":
            metrics_sink.update({
                "steps": record.get("steps"),
                "tool_calls": record.get("tool_calls"),
                "tripartite_status": record.get("tripartite_status"),
                "agent_duration_sec": record.get("duration_sec"),
            })
            return []

        return []


    def _slash_command(
        self, session_id: str, command: str, context: SessionContext
    ) -> Generator[Dict[str, Any], None, None]:
        """Handles deterministic in-chat slash commands."""
        parts = command.split()
        verb = parts[0].lower()

        if verb == "/clear":
            self.clear_session(session_id)
            reply = "Conversation history cleared. Workspace context preserved."
        elif verb == "/status":
            reply = f"```json\n{json.dumps(self.get_status(session_id), indent=2)}\n```"
        elif verb == "/logs":
            window = parts[1] if len(parts) > 1 else "main"
            try:
                reply = f"```\n{self.session_mgr.get_test_logs(test_id=session_id, window=window, lines=80)}\n```"
            except Exception as exc:
                reply = f"Unable to read window '{window}': {exc}"
        elif verb == "/help":
            reply = (
                "**Commands**\n"
                "- `/status` — active session context and tool count\n"
                "- `/logs <window>` — recent output from a tmux window\n"
                "- `/clear` — clear conversation history\n"
                "- `/help` — this message"
            )
        else:
            reply = f"Unknown command `{verb}`. Try `/help`."

        yield {"event": "token", "data": {"text": reply}}
        yield {"event": "done", "data": {"session_id": session_id, "metrics": {}}}
