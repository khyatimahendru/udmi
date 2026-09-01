"""Unit tests for mantis.agent including ReAct multi-step tool-calling loop."""

import os
from unittest.mock import MagicMock
import pytest
from mantis.agent import MantisAgent
from mantis.config import ProviderType


def test_agent_diagnose_stale_cutoff(tmp_path):
    run_dir = tmp_path / "run_stale"
    run_dir.mkdir()
    seq_log = run_dir / "sequence.log"
    seq_log.write_text("""
2026-08-26T12:45:00Z Starting test pointset_publish for AHU-1
2026-08-26T12:45:02Z Dispatched config RC:9a6ddf.00000134
2026-08-26T12:45:08Z Cutoff set: 2026-08-26T12:45:08Z
2026-08-26T12:45:09Z ignoring stale state update 2026-08-26T12:45:06Z
2026-08-26T12:47:08Z Stage timeout after 120s
2026-08-26T12:47:09Z RESULT: FAIL
""")

    agent = MantisAgent()
    res = agent.diagnose_test_failure(
        test_id="pointset_publish",
        device_id="AHU-1",
        site_model="sites/udmi_site_model",
        run_dir=str(run_dir),
    )

    assert res["status"] == "SUCCESS"
    assert "Sequencer timed out" in res["root_cause"]
    assert res["competing_hypotheses"]["Stale State Cutoff Rejection"]["status"] == "CONFIRMED"
    assert res["competing_hypotheses"]["Jackson Deserialization Failure"]["status"] == "REFUTED"
    assert "sequenceDiagram" in res["report"]


def test_agent_diagnose_jackson_error(tmp_path):
    run_dir = tmp_path / "run_jackson"
    run_dir.mkdir()
    seq_log = run_dir / "sequence.log"
    seq_log.write_text("""
2026-08-26T12:45:00Z Starting test pointset_publish for AHU-1
2026-08-26T12:45:02Z UnrecognizedPropertyException: Unrecognized field "invalid_key" (class udmi.schema.Metadata)
2026-08-26T12:45:03Z RESULT: FAIL
""")

    agent = MantisAgent()
    res = agent.diagnose_test_failure(
        test_id="pointset_publish",
        device_id="AHU-1",
        site_model="sites/udmi_site_model",
        run_dir=str(run_dir),
    )

    assert res["status"] == "SUCCESS"
    assert res["competing_hypotheses"]["Jackson Deserialization Failure"]["status"] == "CONFIRMED"
    assert res["competing_hypotheses"]["Stale State Cutoff Rejection"]["status"] == "REFUTED"


def test_agent_run_deterministic_schema_query():
    agent = MantisAgent()
    agent.config.provider_override = ProviderType.OFFLINE_DETERMINISTIC
    out = agent.run("What are the required fields in pointset schema?")
    assert "Schema: `pointset`" in out or "pointset" in out


def test_agent_run_deterministic_site_model_query():
    agent = MantisAgent()
    agent.config.provider_override = ProviderType.OFFLINE_DETERMINISTIC
    out = agent.run("Validate site model sites/udmi_site_model")
    assert "Site Model: `sites/udmi_site_model`" in out
    assert "AHU-1" in out


def test_agent_run_deterministic_test_execution_no_session():
    agent = MantisAgent()
    agent.config.provider_override = ProviderType.OFFLINE_DETERMINISTIC
    agent.session_mgr.list_test_setups = MagicMock(return_value=[])
    agent.session_mgr.is_session_active = MagicMock(return_value=False)
    out = agent.run("Run pointset_publish for device AHU-1")
    assert "not running" in out or "Start an isolated environment" in out


def test_agent_run_deterministic_test_execution_with_active_session():
    agent = MantisAgent()
    agent.config.provider_override = ProviderType.OFFLINE_DETERMINISTIC
    agent.session_mgr.is_session_active = MagicMock(return_value=True)
    agent.session_mgr.get_session_info = MagicMock(return_value={
        "session_name": "udmi_dev_1",
        "ports": {"mqtt": 28430},
        "project_spec": "//mqtt/localhost:28430",
    })
    agent.session_mgr.start_session_process = MagicMock(return_value={"status": "STARTED"})

    out = agent.run("Run pointset_publish for device AHU-1 in session dev_1")
    assert "Launched sequencer test" in out
    assert "AHU-1" in out
    assert "pointset_publish" in out
    agent.session_mgr.start_session_process.assert_called_once()


def test_agent_run_deterministic_test_execution_cloud_endpoint():
    agent = MantisAgent()
    agent.config.provider_override = ProviderType.OFFLINE_DETERMINISTIC
    agent.session_mgr.is_session_active = MagicMock(return_value=True)
    agent.session_mgr.start_session_process = MagicMock(return_value={"status": "STARTED"})

    out = agent.run("Run test pointset_publish for AHU-1 against //gbos/bos-platform-dev/faucetsdn")
    assert "Launched sequencer test" in out
    assert "AHU-1" in out
    assert "pointset_publish" in out
    assert "//gbos/bos-platform-dev/faucetsdn" in out
    agent.session_mgr.start_session_process.assert_called_once()


def test_agent_run_deterministic_test_execution_gref_with_plus_suffix():
    agent = MantisAgent()
    agent.config.provider_override = ProviderType.OFFLINE_DETERMINISTIC
    agent.session_mgr.is_session_active = MagicMock(return_value=True)
    agent.session_mgr.start_session_process = MagicMock(return_value={"status": "STARTED"})

    out = agent.run("Run test pointset_publish for AHU-1 against //gref/bos-platform-staging+heykhyati")
    assert "Launched sequencer test" in out
    assert "AHU-1" in out
    assert "pointset_publish" in out
    assert "//gref/bos-platform-staging+heykhyati" in out
    agent.session_mgr.start_session_process.assert_called_once()


# ------------------------------------------------------------------------------
# Mock ReAct Cognitive Loop Tests
# ------------------------------------------------------------------------------

class MockFunctionCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class MockCandidate:
    def __init__(self, content):
        self.content = content


class MockContent:
    def __init__(self, role, parts):
        self.role = role
        self.parts = parts


class MockResponse:
    def __init__(self, text=None, function_calls=None):
        self.text = text
        self.function_calls = function_calls or []
        self.candidates = [MockCandidate(MockContent("model", []))]


class MockModels:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0
        self.calls = []

    def generate_content(self, model, contents, config):
        self.call_count += 1
        self.calls.append((model, contents, config))
        if self.responses:
            return self.responses.pop(0)
        return MockResponse(text="Default fallback")


class MockGenAIClient:
    def __init__(self, responses):
        self.models = MockModels(responses)


def test_agent_react_tool_calling_loop():
    # Step 1: Model calls inspect_udmi_schema
    resp_step1 = MockResponse(
        text=None,
        function_calls=[MockFunctionCall(name="inspect_udmi_schema", args={"schema_name": "pointset"})],
    )
    # Step 2: Model receives tool output and emits final answer
    resp_step2 = MockResponse(
        text="The pointset schema defines point dictionaries and sample telemetry structures.",
        function_calls=[],
    )

    mock_client = MockGenAIClient([resp_step1, resp_step2])
    agent = MantisAgent(client=mock_client)

    # Force provider to Vertex AI so _run_llm is triggered
    agent.config.provider_override = ProviderType.VERTEX_AI

    chunks = []
    output = agent._run_llm(
        prompt="Tell me about the pointset schema",
        stream_callback=chunks.append,
    )

    assert "The pointset schema defines point dictionaries" in output
    assert mock_client.models.call_count == 2
    # Verify tools were provided in config
    _, _, config = mock_client.models.calls[0]
    assert config.tools is not None


def test_agent_react_tool_error_resilience():
    # Step 1: Model calls a tool with invalid name
    resp_step1 = MockResponse(
        text=None,
        function_calls=[MockFunctionCall(name="non_existent_tool", args={})],
    )
    # Step 2: Model handles error and synthesizes
    resp_step2 = MockResponse(
        text="Handled tool error gracefully.",
        function_calls=[],
    )

    mock_client = MockGenAIClient([resp_step1, resp_step2])
    agent = MantisAgent(client=mock_client)

    output = agent._run_llm(
        prompt="Execute invalid action",
    )

    assert output == "Handled tool error gracefully."
    assert mock_client.models.call_count == 2


class MockStreamChunk:
    def __init__(self, text="", function_calls=None, candidates=None):
        self.text = text
        self.function_calls = function_calls or []
        self.candidates = candidates or []


class MockStreamingModels:
    def __init__(self, stream_chunks):
        self.stream_chunks = stream_chunks
        self.call_count = 0

    def generate_content_stream(self, model, contents, config):
        self.call_count += 1
        for chunk in self.stream_chunks:
            yield chunk


def test_agent_react_streaming_token_chunks():
    chunks_data = [
        MockStreamChunk(text="The "),
        MockStreamChunk(text="pointset "),
        MockStreamChunk(text="schema "),
        MockStreamChunk(text="is "),
        MockStreamChunk(text="valid."),
    ]
    client = MagicMock()
    client.models = MockStreamingModels(chunks_data)
    agent = MantisAgent(client=client)

    received_tokens = []
    output = agent._run_llm(
        prompt="Describe pointset",
        stream_callback=received_tokens.append,
    )

    assert output == "The pointset schema is valid."
    assert received_tokens == ["The ", "pointset ", "schema ", "is ", "valid."]
    assert client.models.call_count == 1


@pytest.mark.anyio
async def test_agent_run_async():
    agent = MantisAgent()
    out = await agent.run_async("What are the required fields in pointset schema?")
    assert "Schema: `pointset`" in out or "pointset" in out


def test_agent_metrics_tracking():
    resp = MockResponse(text="Analysis complete", function_calls=[])
    mock_client = MockGenAIClient([resp])
    agent = MantisAgent(client=mock_client)

    from mantis.context import ContextManager
    ctx_mgr = ContextManager()
    out = agent._run_llm("Analyze test run", context_mgr=ctx_mgr)

    assert out == "Analysis complete"
    assert ctx_mgr.context.metrics is not None
    assert ctx_mgr.context.metrics.total_steps == 1
    assert ctx_mgr.context.metrics.api_calls_count == 1
    assert ctx_mgr.context.metrics.total_duration_sec >= 0.0


def test_agent_api_retry_resilience():
    agent = MantisAgent()
    mock_models = MagicMock()
    # Fail once with 429, then succeed
    mock_models.generate_content.side_effect = [
        RuntimeError("429 ResourceExhausted: Quota exceeded"),
        MockResponse(text="Success after retry", function_calls=[]),
    ]

    res = agent._call_api_with_retry(
        client_models=mock_models,
        method_name="generate_content",
        model="gemini-2.0-pro",
        contents=[],
        config={},
        max_retries=2,
        base_delay=0.01,
    )

    assert res.text == "Success after retry"
    assert mock_models.generate_content.call_count == 2


