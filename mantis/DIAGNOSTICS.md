# MANTIS Autonomous Diagnostics & Adversarial Critique Specification

This document defines the cognitive diagnostic architecture, built-in adversarial self-critique loop, gateway failure heuristics, visual diagramming standards, and support bundle handling mechanisms of Mantis.

---

## 1. The Autonomous Diagnostic Lifecycle

Every diagnostic evaluation in Mantis executes through a deterministic 3-phase cognitive cycle:

```
[Target Test Failure / Log Slice / Support Bundle]
                        │
                        ▼
   [Phase 1: Evidence Harvesting & Deterministic Extraction]
   (Extracts chronological logs, transaction IDs, cutoff deltas, gateway hops)
                        │
                        ▼
   [Phase 2: Built-in Adversarial Self-Audit (Critic)]
   (Claim-by-claim verification matrix, proving vs refuting rival theories)
                        │
                        ├──> Are all claims verified by evidence?
                        │       │
                        │       ├── [No: Refuted / Leaky] ──> Revise Hypothesis & Re-Probe
                        │       │
                        ▼       ▼
   [Phase 3: Verified Synthesis & Visual Artifacts]
   (Emits concise report, optional Mermaid timeline, and actionable fix)
```

---

## 2. Phase 1: Evidence Harvesting & Deterministic Extraction

Before invoking generative reasoning models, Mantis programmatically harvests and structures ground-truth evidence:

1. **Chronological Event Slicing**: Slices raw `sequence.log`, `device_system.log`, `pubber.log`, and `udmis.log` to the exact test execution time bounds (`start_test` to `terminating_test`).
2. **Transaction Echo Mapping**: Tracks configuration transactions (`RC:...`) dispatched by the sequencer and checks if the device acknowledged the exact ID in its reported state.
3. **Cutoff Threshold Resolution**: Extracts the sequencer's `stale state cutoff threshold` and calculates the delta against device state timestamps.
4. **Telemetry Cadence Sampling**: Computes the mean interval between sequential pointset events to identify fixed driver sample rate mismatches.
5. **Gateway Routing Trace**: For proxy devices, traces packets across the gateway bridge to verify whether a failure occurred on the broker connection or on the field bus.

---

## 3. Phase 2: Built-in Adversarial Self-Audit

The Critic evaluates the candidate hypothesis against an explicit **Claim-by-Claim Verification Matrix**.

### 3.1. Verification Matrix Structure

Each factual assertion is classified into one of three states:

* `CONFIRMED`: Substantiated by parsed timestamp, exact log line, schema property, or JSON syntax check.
* `REFUTED`: Disproven by contradictory evidence in raw logs or schemas.
* `UNVERIFIED ASSUMPTION`: Lacks direct evidence; must be either proven through additional tool probing or purged from the analysis.

### 3.2. Mandatory Rival Hypothesis Invalidation

The Critic must evaluate and explicitly document the status of adjacent failure modes:

| Failure Hypothesis | Verification Method | Proof Requirement |
| :--- | :--- | :--- |
| **Jackson Deserialization Failure** | Parse `metadata.json` with Python JSON decoder and check line/column indices. | Syntax error string from Jackson parser in `sequence.log`. |
| **Stale State Cutoff Rejection** | Compare sequencer cutoff timestamp against device `state.timestamp`. | Explicit `ignoring stale state update` log entry. |
| **Telemetry Cadence Mismatch** | Calculate average delta between consecutive `events_pointset` messages. | Average interval $> 120\text{s}$ against standard test wait timeout. |
| **Gateway Proxy Bus Drop** | Correlate gateway device state with sub-device state packets. | Gateway reports online state, but sub-device `pointset` stream is absent. |
| **Transport / Broker Congestion** | Scan Mosquitto and UDMIS logs for outbound channel queue drops. | `inFlight tokens` congestion or socket drop notices. |

---

## 4. Gateway & Proxy Failure Heuristics

For multi-device building networks involving BACnet, Modbus, or proprietary serial gateways:

```
+-------------------+      MQTT      +--------------------+      RS-485 / IP      +-------------------+
|  UDMI Cloud/Host  | <------------> |  Gateway Device    | <-------------------> |  Proxy Sub-Device |
|  (Broker/UDMIS)   |                |  (e.g., GAT-101)   |                       |  (e.g., VAV-04)   |
+-------------------+                +--------------------+                       +-------------------+
```

Mantis applies a 3-step isolation rule:
1. **Verify Gateway Connectivity**: Check if the gateway device itself successfully publishes `state_system` and receives configuration updates.
2. **Verify Proxy Binding**: Inspect `sites/<site>/devices/<proxy_id>/metadata.json` to confirm `gateway_id` is defined and correctly references the gateway device.
3. **Isolate Bus Timeout vs Protocol Drop**:
   * If the gateway emits `gateway_proxy_error` or logs serial frame CRC errors $\rightarrow$ **Field Bus Communication Failure**.
   * If the gateway receives the config transaction but omits the sub-device echo in its aggregated state $\rightarrow$ **Gateway Firmware / Driver State Translation Bug**.

---

## 5. Behavioral Differential Log Analysis

Differential log analysis maps the sequence of discrete protocol state events between a reference passing run and the failing target run to identify the exact state machine divergence.

```
Step | Protocol Checkpoint     | Baseline Run (Pass)             | Target Run (Fail)               | Delta
-----+-------------------------+---------------------------------+---------------------------------+------------------------
1    | TEST_START              | Starting test pointset_publish  | Starting test pointset_publish  | Aligned
2    | CONFIG_DISPATCH         | Dispatched config RC:9a6ddf.001 | Dispatched config RC:9a6ddf.001 | Aligned
3    | STAGE_WAIT_START        | Waiting for config sync         | Waiting for config sync         | Aligned
4    | STATE_CUTOFF_SET        | Cutoff set: 12:40:00Z (Batch)   | Cutoff set: 12:45:08Z (Stand.)  | DIVERGENCE POINT
5    | STATE_RECEIVED          | Received state (ts: 12:45:06Z)  | Received state (ts: 12:45:06Z)  | Aligned
6    | STALE_STATE_IGNORED     | (None - accepted by cutoff)     | Ignoring stale state update     | DIVERGENCE POINT
7    | TIMEOUT_FAILURE         | (None)                          | Stage timeout after 120s        | Cascading Failure
8    | TEST_RESULT             | RESULT: PASS                    | RESULT: FAIL                    | Final Outcome
```

---

## 6. Visual Artifact & Diagramming Standards

When generating diagnostic summaries or export artifacts, Mantis renders complex interactions using standard diagrams:

### 6.1. Protocol Synchronization (Mermaid Sequence Diagram)
```mermaid
sequenceDiagram
    participant S as Sequencer
    participant U as UDMIS
    participant B as Mosquitto Broker
    participant D as Device (Pubber)

    S->>U: Dispatches config (RC:9a6ddf.00000134)
    U->>B: Routes config packet
    B->>D: Delivers config update
    Note over S: Sets Cutoff: 12:45:08Z
    D->>B: Publishes state (Timestamp: 12:45:06Z)
    B->>U: Forwards state
    U->>S: Delivers state update
    Note over S: Ignoring stale state (12:45:06Z < 12:45:08Z)
    Note over S: Timeout Failure (120s expired)
```

---

## 7. Support Bundle Ingestion & Automated Credential Redaction

When triaging external support bundles (`support_bundle.zip` or `.tgz`):

### 7.1. Expected Bundle Directory Layout
```
support_bundle/
├── triage_manifest.json      # Metadata: site name, target device, failed test name
├── site_model/               # Site configuration and device metadata
│   ├── cloud_iot_config.json
│   └── devices/<device_id>/metadata.json
└── logs/                     # Captured log streams
    ├── sequence.log
    ├── udmis.log
    ├── device_system.log
    └── pubber.log
```

### 7.2. Automated Credential Redaction Protocol
Before parsing log streams or site models into memory or generative models, Mantis automatically sanitizes:
* **RSA Private Keys**: Any file matching `*.pem` or block containing `-----BEGIN RSA PRIVATE KEY-----` is stripped.
* **MQTT Passwords & Secrets**: Passwords in `cloud_iot_config.json` or connection URLs (`mqtt://user:pass@...`) are masked as `mqtt://user:***@...`.
* **GCP Service Account Tokens**: OAuth bearer tokens and GCP private service account keys are replaced with `[REDACTED_GCP_KEY]`.

---

## 8. Concise Output Report Format

Diagnostic reports generated by Mantis present verified findings with zero extraneous boilerplate:

```markdown
### Failure Diagnosis: `<Device ID>` / `<Test ID>`

* **Root Cause**: [1-2 sentence technical explanation of the verified failure mechanism].
* **Evidence**:
  - [Exact log line / timestamp / transaction ID proof]
  - [Exact schema violation, Jackson error, or cutoff delta]
* **Fix**:
  - [Direct executable command or configuration patch]
```
