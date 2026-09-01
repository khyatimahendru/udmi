"""Mantis ReAct Cognitive Planner and Built-in Adversarial Critique Engine."""

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from mantis.config import CONFIG, ModelTier, ProviderType
from mantis.skills import SkillManager
from mantis.tools.artifacts import (
    discover_test_runs,
    extract_log_slice,
    extract_timeline,
    ingest_support_bundle,
)
from mantis.tools.differential import compare_test_runs
from mantis.tools.patcher import patch_site_model
from mantis.tools.schemas import inspect_udmi_schema, list_udmi_schemas
from mantis.tools.site_models import inspect_site_model
from mcp.session_manager import SessionManager


from mantis.context import ContextManager
from mantis.models import SessionContext
from mantis.tools.diagnostics import diagnose_test_failure as deterministic_diagnose


class MantisAgent:
    """Autonomous diagnostic agent and ReAct cognitive core for UDMI."""

    def __init__(self, udmi_root: Optional[str] = None, client: Optional[Any] = None):
        if udmi_root is not None:
            self.udmi_root = os.path.abspath(udmi_root)
        else:
            self.udmi_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        self.config = CONFIG
        self.client = client
        self.skills = SkillManager(udmi_root=self.udmi_root)
        self.session_mgr = SessionManager(udmi_root=self.udmi_root)
        self.active_site_model = "sites/udmi_site_model"
        self.active_session_id: Optional[str] = None

    # --------------------------------------------------------------------------
    # 3-Phase Cognitive Diagnostic Engine
    # --------------------------------------------------------------------------

    def diagnose_test_failure(
        self,
        test_id: str,
        device_id: str,
        site_model: str = "sites/udmi_site_model",
        run_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes the mandatory 3-phase diagnostic cycle with built-in adversarial self-audit."""
        return deterministic_diagnose(
            test_id=test_id,
            device_id=device_id,
            site_model=site_model,
            run_dir=run_dir,
            udmi_root=self.udmi_root,
        )

    # --------------------------------------------------------------------------
    # Universal Intent Parser & Dispatcher
    # --------------------------------------------------------------------------

    def run_headless(self, prompt_or_file: str) -> str:
        """Executes any instruction or support bundle headless and returns output."""
        clean_input = prompt_or_file.strip()

        # Check if file path passed directly (e.g. support bundle or log)
        if os.path.isfile(clean_input):
            if clean_input.endswith(".zip") or clean_input.endswith(".tar.gz") or clean_input.endswith(".tgz"):
                return self._handle_bundle_triage(clean_input)
            elif clean_input.endswith(".json") and "metadata" in clean_input:
                return f"Inspecting metadata file: {clean_input}\n" + json.dumps(
                    inspect_site_model(os.path.dirname(os.path.dirname(os.path.dirname(clean_input)))), indent=2
                )

        return self.run(clean_input)

    def run(
        self,
        prompt: str,
        context: Optional[SessionContext] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Executes a natural language prompt with stateful multi-turn conversational memory."""
        q = prompt.strip()
        if context is not None:
            ctx_mgr = ContextManager(context=context, udmi_root=self.udmi_root)
        else:
            ctx_mgr = ContextManager(udmi_root=self.udmi_root)
            if self.active_session_id and not ctx_mgr.context.active_session_id:
                ctx_mgr.context.active_session_id = self.active_session_id

        ctx_mgr.add_user_message(q)

        # If LLM API credentials are configured, try generative client
        if self.config.provider in (ProviderType.VERTEX_AI, ProviderType.AI_STUDIO) or self.client is not None:
            try:
                res = self._run_llm(q, context_mgr=ctx_mgr, stream_callback=stream_callback)
                ctx_mgr.add_assistant_message(res)
                return res
            except Exception as e:
                # Graceful fallback to deterministic engine on network/API/ADC failure
                fallback_msg = (
                    f"[Note: AI Provider '{self.config.provider.value}' unavailable ({e}).\n"
                    f"To use Vertex AI, ensure ADC is authenticated: 'gcloud auth application-default login'\n"
                    f"Or export an API key: 'export GEMINI_API_KEY=\"your-key\"'\n"
                    f"Switching to deterministic engine]\n"
                )
                if stream_callback:
                    stream_callback(fallback_msg)
                res = fallback_msg + self._run_deterministic(q, context_mgr=ctx_mgr, stream_callback=stream_callback)
                ctx_mgr.add_assistant_message(res)
                return res

        res = self._run_deterministic(q, context_mgr=ctx_mgr, stream_callback=stream_callback)
        ctx_mgr.add_assistant_message(res)
        return res

    # --------------------------------------------------------------------------
    # Deterministic Execution Pipeline
    # --------------------------------------------------------------------------

    def _run_deterministic(
        self,
        query: str,
        context_mgr: Optional[ContextManager] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Deterministic, factual execution of queries with contextual antecedent resolution."""
        q_lower = query.lower()
        active_dev = context_mgr.context.active_device_id if context_mgr else None
        active_test = context_mgr.context.active_test_id if context_mgr else None
        active_site = context_mgr.context.active_site_model if context_mgr else self.active_site_model
        active_sess = context_mgr.context.active_session_id if context_mgr else self.active_session_id

        def emit(text: str) -> None:
            if stream_callback:
                stream_callback(text)

        # 1. Environment Management (Start / Ensure / Bring up / Spin up / Setup)
        if any(w in q_lower for w in ("start", "ensure", "provision", "bring up", "spin up", "launch", "setup", "deploy", "up ")) and (
            any(w in q_lower for w in ("stack", "environment", "local", "infra", "infrastructure", "setup", "sequencer"))
        ) and not ("why" in q_lower or "fail" in q_lower):
            emit("Mantis: Provisioning isolated environment...\n")
            test_id = self._extract_word(query, r"(?:environment|session|setup|stack)\s+['\"]?([a-zA-Z0-9_-]+)['\"]?", default=active_sess or "dev_1")
            dut_match = re.search(r"dut\s+([a-zA-Z0-9_-]+)", query, re.IGNORECASE)
            dut = dut_match.group(1) if dut_match else active_dev
            site_match = re.search(r"(sites/[a-zA-Z0-9_\-\./]+)", query)
            site = site_match.group(1) if site_match else active_site

            added = ["validator"] if "validator" in q_lower else None
            exclude = []
            for svc in ("udmis", "influxdb", "postgres", "butler"):
                if f"without {svc}" in q_lower or f"!{svc}" in q_lower:
                    exclude.append(svc)

            try:
                res = self.session_mgr.ensure_test_setup(
                    test_id=test_id,
                    site_model=site,
                    dut_device_id=dut,
                    exclude=exclude or None,
                    added=added,
                )
                self.active_session_id = test_id
                if context_mgr:
                    context_mgr.context.active_session_id = test_id
                    if dut:
                        context_mgr.context.active_device_id = dut
                    context_mgr.save_context()
                ports = res.get("ports", {})
                out = (
                    f"Mantis: Provisioning isolated environment '{res['session_name']}'...\n"
                    f"  * Allocated Port Block: MQTT={ports.get('mqtt')}, etcd={ports.get('etcd')}, "
                    f"influx={ports.get('influx')}, postgres={ports.get('postgres')}\n"
                    f"  * Launched Tmux Session: '{res['session_name']}' {res.get('windows', [])}\n"
                    f"  * Control Plane Ready: Mosquitto online, certificates generated, UDMIS ready.\n"
                )
                if dut:
                    out += f"  * DUT: {dut} running in window 'dut'.\n"
                out += f"Environment '{test_id}' is ready at {res.get('connection_url')}."
                emit(out)
                return out
            except Exception as e:
                err = f"Failed to start environment: {e}"
                emit(err)
                return err

        # 2. Environment Teardown (Stop / Terminate)
        if ("stop" in q_lower or "terminate" in q_lower or "kill" in q_lower) and (
            "environment" in q_lower or "stack" in q_lower or "session" in q_lower
        ):
            test_id = self._extract_word(query, r"(?:environment|session|setup)\s+['\"]?([a-zA-Z0-9_-]+)['\"]?", default=active_sess or "dev_1")
            res = self.session_mgr.terminate_test_setup(test_id)
            out = f"Environment '{test_id}' ({res.get('session_name')}) terminated."
            emit(out)
            return out

        # 3. Test Execution Triggering
        if "run " in q_lower and (" on " in q_lower or " for " in q_lower or "test " in q_lower) and not ("why" in q_lower or "fail" in q_lower):
            test_id = self._extract_word(query, r"run\s+(?:test\s+)?([a-z0-9_]{4,})", default=active_test or "pointset_publish")
            device_id = self._extract_word(query, r"(?:device\s+|for\s+(?:device\s+)?|on\s+(?:device\s+)?)([A-Za-z0-9_-]{3,})", default=active_dev or "AHU-1")
            target_spec = self._extract_word(query, r"(//[a-zA-Z0-9_\-\./:\+@]+)", default=None)
            site = self._extract_word(query, r"(sites/[a-zA-Z0-9_\-\./]+)", default=active_site or "sites/udmi_site_model")
            
            if target_spec:
                res = self.session_mgr.run_sequencer_test(
                    test_name=test_id,
                    device_id=device_id,
                    target_spec=target_spec,
                    site_model=site,
                )
                if context_mgr:
                    context_mgr.context.active_test_id = test_id
                    context_mgr.context.active_device_id = device_id
                    context_mgr.context.active_site_model = site
                    context_mgr.context.active_session_id = res.get("session_id")
                    context_mgr.save_context()
                out = (
                    f"Mantis: Launched sequencer test '{test_id}' for {device_id} against '{res.get('target_spec')}'...\n"
                    f"  * Session: '{res.get('session_id')}' (Window: 'sequencer')\n"
                    f"  * Command: {res.get('command')}\n"
                    f"Use `/logs sequencer` to inspect live progress or ask 'Why did it fail?' for root-cause diagnosis."
                )
                emit(out)
                return out

            target_sess = active_sess or self.active_session_id
            if not target_sess:
                active_setups = self.session_mgr.list_test_setups()
                if active_setups:
                    target_sess = active_setups[0].get("test_id")

            if context_mgr:
                context_mgr.context.active_test_id = test_id
                context_mgr.context.active_device_id = device_id
                context_mgr.context.active_site_model = site
                if target_sess:
                    context_mgr.context.active_session_id = target_sess
                context_mgr.save_context()

            if target_sess and self.session_mgr.is_session_active(self.session_mgr.sanitize_session_name(target_sess)):
                sess_info = self.session_mgr.get_session_info(target_sess) or {}
                ports = sess_info.get("ports", {})
                mqtt_port = ports.get("mqtt", self.session_mgr.derive_port_block(target_sess))
                project_spec = sess_info.get("project_spec", f"//mqtt/localhost:{mqtt_port}")
                
                cmd = f"bin/sequencer '{site}' '{project_spec}' '{device_id}' '{test_id}'"
                try:
                    self.session_mgr.start_session_process(
                        test_id=target_sess,
                        window="sequencer",
                        command=cmd,
                    )
                    out = (
                        f"Mantis: Launched sequencer test '{test_id}' for {device_id} in session '{target_sess}'...\n"
                        f"  * Semantic Window: 'sequencer'\n"
                        f"  * Target Spec: {project_spec}\n"
                        f"  * Command: {cmd}\n"
                        f"Use `/logs sequencer` to inspect live progress or ask 'Why did it fail?' for root-cause diagnosis."
                    )
                except Exception as e:
                    out = f"Mantis: Failed to launch sequencer in session '{target_sess}': {e}"
            else:
                out = (
                    f"Mantis: Target environment session '{target_sess or 'dev_1'}' is not running.\n"
                    f"Start an isolated environment first (e.g. `bin/mantis \"Start isolated local environment with DUT {device_id}\"`)."
                )
            emit(out)
            return out

        # 4. Diagnostic Triage / Root Cause Analysis
        if "why did" in q_lower or "fail" in q_lower or "diagnos" in q_lower or "triage" in q_lower:
            device_id = self._extract_word(query, r"(?:device\s+|for\s+(?:device\s+)?|on\s+(?:device\s+)?)([A-Za-z0-9_-]{3,})", default=active_dev or "AHU-1")
            test_id = self._extract_word(query, r"(?:did|run\s+(?:test\s+)?|test\s+)([a-z0-9_]{4,})", default=active_test or "pointset_publish")
            site = self._extract_word(query, r"(sites/[a-zA-Z0-9_\-\./]+)", default=active_site or "sites/udmi_site_model")

            if context_mgr:
                context_mgr.context.active_device_id = device_id
                context_mgr.context.active_test_id = test_id
                context_mgr.context.active_site_model = site

            emit(f"Mantis: Analyzing logs, timestamps, and schema definitions for {device_id} / {test_id}...\n\n")
            diag = self.diagnose_test_failure(
                test_id=test_id,
                device_id=device_id,
                site_model=site,
            )
            report = diag.get("report", "")
            emit(report)
            return report

        # 5. Schema Inspection
        if "schema" in q_lower or "fields in" in q_lower or "inspect schema" in q_lower:
            schema_name = self._extract_word(query, r"([a-z0-9_]+)(?:\.json|\s+schema)", default="pointset")
            res = inspect_udmi_schema(schema_name=schema_name)
            if res.get("status") == "SUCCESS":
                reqs = res.get("required", [])
                props = list(res.get("schema", {}).get("properties", {}).keys()) if isinstance(res.get("schema"), dict) else []
                out = (
                    f"### Schema: `{res.get('schema_name')}`\n"
                    f"* **Title**: {res.get('title')}\n"
                    f"* **Description**: {res.get('description') or 'Authoritative UDMI schema'}\n"
                    f"* **Required Fields**: {reqs if reqs else '(None required)'}\n"
                    f"* **Properties**: {', '.join(props[:20]) if props else 'N/A'}\n"
                    f"* **File**: `{res.get('schema_file')}`"
                )
            else:
                out = f"Error inspecting schema: {res.get('error')}"
            emit(out)
            return out

        # 6. Site Model Inspection & Validation
        if "site model" in q_lower or "validate site" in q_lower or "inspect device" in q_lower:
            site = self._extract_word(query, r"(sites/[a-zA-Z0-9_\-\./]+)", default=active_site)
            device = self._extract_word(query, r"(?:device|for)\s+([A-Z0-9_-]{3,})", default=active_dev)
            res = inspect_site_model(site_model=site, device_id=device)
            if res.get("status") == "SUCCESS":
                if device:
                    out = (
                        f"### Device Metadata: `{device}`\n"
                        f"* **Site Model**: `{site}`\n"
                        f"* **Points Defined**: {res.get('point_count')} points ({', '.join(res.get('points', [])[:10])})\n"
                        f"* **System**: {json.dumps(res.get('system', {}))}\n"
                        f"* **Gateway**: {res.get('gateway', {}).get('gateway_id', 'Direct device')}"
                    )
                else:
                    out = (
                        f"### Site Model: `{site}`\n"
                        f"* **Total Devices**: {res.get('device_count')}\n"
                        f"* **Devices**: {', '.join(res.get('devices', [])[:15])}\n"
                        f"* **Status**: Valid site model structure"
                    )
            else:
                out = f"Error inspecting site model: {res.get('error')}"
            emit(out)
            return out

        # 7. Configuration & Metadata Patching
        if "set " in q_lower or "patch" in q_lower or "update " in q_lower:
            device = self._extract_word(query, r"(?:for|device)\s+([A-Z0-9_-]{3,})", default=active_dev or "AHU-1")
            site = self._extract_word(query, r"(sites/[a-zA-Z0-9_\-\./]+)", default=active_site)

            # Check sample_rate_sec
            sr_match = re.search(r"sample_rate_sec\s*(?:to|=)?\s*([0-9]+)", query, re.IGNORECASE)
            patch_data: Dict[str, Any] = {}
            if sr_match:
                rate = int(sr_match.group(1))
                patch_data = {"pointset": {"sample_rate_sec": rate}}
            elif "nostate" in q_lower:
                patch_data = {"testing": {"nostate": True}}

            if patch_data:
                res = patch_site_model(site_model=site, device_id=device, patch_data=patch_data)
                out = (
                    f"### Applied Configuration Patch for `{device}`\n"
                    f"* **File**: `{res.get('file')}`\n"
                    f"* **Backup Created**: `{res.get('backup')}`\n"
                    f"* **Diff**:\n```diff\n{res.get('diff')}```"
                )
            else:
                out = f"Could not parse configuration patch fields from '{query}'."
            emit(out)
            return out

        # 8. Multi-Run Evaluation & Stability
        if "eval" in q_lower or "stability" in q_lower:
            from mantis.tools.diagnostics import evaluate_test_stability
            res = evaluate_test_stability(site_model=active_site, udmi_root=self.udmi_root)
            out = res.get("summary_report", "")
            emit(out)
            return out

        # 9. Differential Comparison
        if "compare" in q_lower or "diff" in q_lower:
            runs = discover_test_runs(udmi_root=self.udmi_root)
            target = runs[0]["path"] if runs else "out"
            res = compare_test_runs(target_run=target)
            out = f"### Behavioral Differential Analysis\n\n{res.get('differential_table', '')}"
            emit(out)
            return out

        # Default fallback: Answer with skill references
        skills_summary = self.skills.get_system_prompt_catalog()
        out = (
            f"Mantis processed query: '{query}'\n\n"
            f"{skills_summary}\n\n"
            f"Use `bin/mantis \"<instruction>\"` for test triage, provisioning, schema queries, or site model patching."
        )
        emit(out)
        return out

    async def run_async(
        self,
        prompt: str,
        context: Optional[SessionContext] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Asynchronously executes a natural language prompt with non-blocking execution."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self.run, prompt, context, stream_callback
        )

    # --------------------------------------------------------------------------
    # Generative AI Execution Pipeline
    # --------------------------------------------------------------------------

    def _call_api_with_retry(
        self,
        client_models: Any,
        method_name: str,
        model: str,
        contents: Any,
        config: Any,
        max_retries: int = 3,
        base_delay: float = 0.5,
    ) -> Any:
        """Execute client model calls with exponential backoff retry for transient rate limits and network errors."""
        import random
        import time

        last_err = None
        for attempt in range(max_retries):
            try:
                method = getattr(client_models, method_name)
                return method(model=model, contents=contents, config=config)
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                # Check for transient / retryable API errors (429, 503, ResourceExhausted, RateLimit)
                if attempt < max_retries - 1 and any(
                    w in err_str
                    for w in ("429", "503", "resource_exhausted", "quota", "timeout", "unavailable", "rate limit")
                ):
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = (base_delay * (2**attempt)) * jitter
                    time.sleep(sleep_time)
                    continue
                raise
        if last_err:
            raise last_err

    def _run_llm(
        self,
        prompt: str,
        context_mgr: Optional[ContextManager] = None,
        stream_callback: Optional[Callable[[str], None]] = None,
        max_steps: int = 10,
    ) -> str:
        """Executes multi-step ReAct planning using google-genai SDK, token metrics, and dynamic tool execution."""
        import time
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore
        from mantis.models import ExecutionMetrics
        from mantis.tools.registry import get_genai_tools, execute_tool

        start_time = time.time()
        metrics = ExecutionMetrics()

        def emit(text: str) -> None:
            if stream_callback:
                stream_callback(text)

        if self.client:
            client = self.client
        elif self.config.provider == ProviderType.VERTEX_AI:
            project = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("GCP_PROJECT", self.config.default_gcp_project))
            location = os.getenv("GOOGLE_CLOUD_REGION", os.getenv("GCP_REGION", self.config.default_gcp_location))
            client = genai.Client(vertexai=True, project=project, location=location)
        else:
            client = genai.Client()

        skills_catalog = self.skills.get_system_prompt_catalog()
        relevant_skills = self.skills.load_skills_for_context(prompt)

        system_instruction = f"""You are Mantis, the autonomous diagnostic agent and management control plane for the Universal Device Management Interface (UDMI).

{skills_catalog}

{relevant_skills}

UDMI Architecture & Test Conventions:
- **Site Model (`site_model`)**: ALWAYS a local directory path (e.g. `sites/udmi_site_model` or `sites/faucetsdn`), NEVER a URI starting with `//`. Default is `sites/udmi_site_model`.
- **Target Spec (`target_spec`)**: Target cloud or broker connection spec (e.g. `//gbos/bos-platform-dev/faucetsdn`, `//gcp/project/registry`, `//mqtt/localhost:18833`).
- **Test Execution**: To run sequencer tests, call `run_sequencer_test(test_name=..., device_id=..., target_spec=..., site_model=...)`.
- **Cloud vs Local**: Cloud endpoints (`//gbos/...`, `//gcp/...`, `//iotcore/...`) do NOT require `ensure_test_setup` (which is only for local Docker/tmux infrastructure). `run_sequencer_test` executes against remote cloud endpoints directly.

Follow the mandatory 3-Phase Cognitive Diagnostic Cycle:
1. Phase 1: Evidence Harvesting (Use tools to inspect schemas, site models, extract timelines with timestamps, transaction IDs RC:..., cutoff thresholds).
2. Phase 2: Built-in Adversarial Self-Audit (evaluate Claim-by-Claim Verification Matrix with CONFIRMED, REFUTED, or UNVERIFIED ASSUMPTION, and invalidate rival hypotheses).
3. Phase 3: Verified Synthesis (emit concise report format with Root Cause, Evidence, Fix, and optional Visual Diagrams).

Visual Diagram Guidelines:
- **Graphviz (DOT) Diagrams** (` ```dot ` or ` ```graphviz `): Use for topology architectures, device/gateway relationships, site models, and failure causality graphs. The Mantis UI automatically renders these as interactive SVG cards.
- **Mermaid Diagrams** (` ```mermaid `): Use for sequence diagrams, protocol handshakes, and transaction timelines between Sequencer, Broker, and Devices.

You have access to domain tools to inspect the environment, execute tests, query runtime databases, inspect schemas, and triage failures. Use tools to gather empirical evidence before making claims.
"""

        genai_tools = get_genai_tools()
        if context_mgr:
            contents = context_mgr.get_llm_contents(prompt)
        else:
            contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]

        model_name = self.config.get_model_for_tier(ModelTier.PRO)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=genai_tools if genai_tools else None,
            temperature=0.2,
        )

        final_answer = ""

        for step in range(max_steps):
            metrics.total_steps += 1
            metrics.api_calls_count += 1

            step_text = ""
            function_calls = []
            candidate_content = None

            if hasattr(client.models, "generate_content_stream") and stream_callback:
                try:
                    stream = self._call_api_with_retry(
                        client.models,
                        "generate_content_stream",
                        model=model_name,
                        contents=contents,
                        config=config,
                    )
                    for chunk in stream:
                        chunk_text = getattr(chunk, "text", "") or ""
                        if chunk_text:
                            emit(chunk_text)
                            step_text += chunk_text
                        if getattr(chunk, "function_calls", None):
                            function_calls.extend(chunk.function_calls)
                        if getattr(chunk, "candidates", None) and chunk.candidates:
                            candidate_content = chunk.candidates[0].content
                        if getattr(chunk, "usage_metadata", None):
                            um = chunk.usage_metadata
                            metrics.prompt_tokens = getattr(um, "prompt_token_count", metrics.prompt_tokens) or 0
                            metrics.candidates_tokens = getattr(um, "candidates_token_count", metrics.candidates_tokens) or 0
                            metrics.total_tokens = getattr(um, "total_token_count", metrics.total_tokens) or 0
                except Exception:
                    response = self._call_api_with_retry(
                        client.models,
                        "generate_content",
                        model=model_name,
                        contents=contents,
                        config=config,
                    )
                    candidate_content = None
                    if getattr(response, "candidates", None) and response.candidates:
                        candidate_content = response.candidates[0].content
                        if candidate_content and candidate_content.parts:
                            for part in candidate_content.parts:
                                if getattr(part, "text", None):
                                    step_text += part.text
                    function_calls = getattr(response, "function_calls", None) or []
                    if getattr(response, "usage_metadata", None):
                        um = response.usage_metadata
                        metrics.prompt_tokens += getattr(um, "prompt_token_count", 0) or 0
                        metrics.candidates_tokens += getattr(um, "candidates_token_count", 0) or 0
                        metrics.total_tokens += getattr(um, "total_token_count", 0) or 0
                    if step_text:
                        emit(step_text)
            else:
                response = self._call_api_with_retry(
                    client.models,
                    "generate_content",
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                step_text = ""
                function_calls = getattr(response, "function_calls", None) or []
                candidate_content = None
                if getattr(response, "candidates", None) and response.candidates:
                    candidate_content = response.candidates[0].content
                    if candidate_content and candidate_content.parts:
                        for part in candidate_content.parts:
                            if getattr(part, "text", None):
                                step_text += part.text
                            if getattr(part, "function_call", None) and not function_calls:
                                function_calls.append(part.function_call)
                if getattr(response, "usage_metadata", None):
                    um = response.usage_metadata
                    metrics.prompt_tokens += getattr(um, "prompt_token_count", 0) or 0
                    metrics.candidates_tokens += getattr(um, "candidates_token_count", 0) or 0
                    metrics.total_tokens += getattr(um, "total_token_count", 0) or 0
                if not step_text and not function_calls and getattr(response, "text", None):
                    step_text = response.text or ""
                if step_text and not function_calls:
                    emit(step_text)

            if not function_calls:
                # Terminal step: Model emitted final answer
                final_answer = step_text
                break

            # Append model turn with function calls
            if candidate_content:
                contents.append(candidate_content)
            else:
                model_parts = []
                if step_text:
                    model_parts.append(types.Part.from_text(text=step_text))
                for fc in function_calls:
                    model_parts.append(types.Part.from_function_call(name=fc.name, args=fc.args or {}))
                contents.append(types.Content(role="model", parts=model_parts))

            # Execute tool calls
            response_parts = []
            tool_call_sigs = []
            should_break = False

            for call in function_calls:
                call_name = call.name
                call_args = dict(call.args) if call.args else {}
                metrics.tool_calls[call_name] = metrics.tool_calls.get(call_name, 0) + 1
                emit(f"\n[Mantis ReAct Step {step+1}] Calling `{call_name}` with {json.dumps(call_args)}\n")

                if call_name == "ensure_test_setup":
                    emit("  -> Provisioning local UDMI stack (starting Mosquitto, etcd, InfluxDB, PostgreSQL, UDMIS)...\n")
                elif call_name == "run_sequencer_test":
                    emit(f"  -> Launching sequencer test '{call_args.get('test_name')}' for {call_args.get('device_id', 'AHU-1')} against {call_args.get('target_spec', 'local')}...\n")
                elif call_name == "start_session_process":
                    emit(f"  -> Launching process in window '{call_args.get('window', 'sequencer')}'...\n")

                try:
                    tool_output = execute_tool(
                        name=call_name,
                        args=call_args,
                        session_mgr=self.session_mgr,
                        udmi_root=self.udmi_root,
                    )
                except Exception as err:
                    tool_output = {"status": "ERROR", "error": str(err)}

                if isinstance(tool_output, dict):
                    if tool_output.get("status") == "READY":
                        emit(f"  -> Environment '{tool_output.get('test_id')}' is READY at {tool_output.get('connection_url')}\n")
                        self.active_session_id = tool_output.get("test_id")
                        if context_mgr:
                            context_mgr.context.active_session_id = tool_output.get("test_id")
                            context_mgr.save_context()
                    elif tool_output.get("status") == "LAUNCHED":
                        emit(f"  -> Sequencer test '{tool_output.get('test_name')}' LAUNCHED against {tool_output.get('target_spec')} in session '{tool_output.get('session_id')}'\n")
                        self.active_session_id = tool_output.get("session_id")
                        if context_mgr:
                            context_mgr.context.active_session_id = tool_output.get("session_id")
                            context_mgr.context.active_test_id = tool_output.get("test_name")
                            context_mgr.context.active_device_id = tool_output.get("device_id")
                            context_mgr.save_context()
                    elif tool_output.get("status") == "ERROR":
                        emit(f"  -> Tool execution error: {tool_output.get('error')}\n")

                resp_payload = tool_output if isinstance(tool_output, dict) else {"result": tool_output}
                response_parts.append(
                    types.Part.from_function_response(
                        name=call_name,
                        response=resp_payload,
                    )
                )

            contents.append(types.Content(role="user", parts=response_parts))

        if not final_answer:
            final_answer = "Mantis reached maximum tool execution steps without completing synthesis."
            emit(final_answer)

        metrics.total_duration_sec = round(time.time() - start_time, 3)
        if context_mgr:
            context_mgr.context.metrics = metrics
            context_mgr.save_context()

        return final_answer

    # --------------------------------------------------------------------------
    # Helper Utilities
    # --------------------------------------------------------------------------

    def _handle_bundle_triage(self, bundle_file: str) -> str:
        """Ingests a support bundle and performs root-cause analysis."""
        ingest_res = ingest_support_bundle(bundle_file, udmi_root=self.udmi_root)
        if ingest_res.get("status") != "SUCCESS":
            return f"Error ingesting bundle: {ingest_res.get('error')}"

        manifest = ingest_res.get("manifest", {})
        site = manifest.get("site_name", "sites/udmi_site_model")
        device = manifest.get("device_id", "AHU-1")
        test = manifest.get("failed_test", "pointset_publish")

        diag = self.diagnose_test_failure(
            test_id=test,
            device_id=device,
            site_model=site,
            run_dir=ingest_res.get("extracted_dir"),
        )
        return f"Support Bundle Ingestion: `{bundle_file}`\n\n" + diag.get("report", "")

    def _extract_word(self, text: str, pattern: str, default: Optional[str] = None) -> Any:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if val.lower() not in ("for", "with", "on", "at", "to", "in", "the", "a", "an", "of", "and", "is", "by", "from"):
                return val
        return default
