---
name: investigation-strategy
description: Systematic 3-phase investigation lifecycle, adversarial self-audit, rival hypothesis invalidation, and boundary probing in UDMI.
---

# UDMI Autonomous Investigation Strategy

## 1. The 3-Phase Investigation Lifecycle

Every diagnostic evaluation in Mantis executes through a deterministic 3-phase cognitive cycle:

### Phase 1: Evidence Harvesting & Deterministic Extraction
* Slices raw logs to test start and completion bounds.
* Extracts chronological timestamps and transaction IDs (`RC:...`).
* Resolves sequencer stale state cutoff thresholds.
* Calculates average telemetry sample rate (cadence).

### Phase 2: Built-in Adversarial Self-Audit (Critic)
* Evaluates candidate claims against an explicit **Verification Matrix** (`CONFIRMED`, `REFUTED`, `UNVERIFIED ASSUMPTION`).
* Mandates evaluation and refutation of adjacent rival failure hypotheses:
  1. **Jackson Deserialization Failure**: Checks for syntax errors or invalid fields in `metadata.json`.
  2. **Stale State Cutoff Rejection**: Compares sequencer cutoff timestamp with device state timestamp.
  3. **Telemetry Cadence Mismatch**: Checks if sample interval exceeds test wait timeout.
  4. **Gateway Proxy Bus Drop**: Checks if field bus communication between gateway and sub-device failed.
  5. **Transport / Broker Congestion**: Checks for broker socket drops or in-flight queue overflow.

### Phase 3: Verified Synthesis
* Emits concise diagnostic report:
  - Root Cause
  - Exact Log / Timestamp Evidence
  - Actionable Fix / Command
* Generates Mermaid sequence diagram when helpful.
