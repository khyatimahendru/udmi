[**UDMI**](../../../) / [**Docs**](../../) / [**Specs**](../) / [**Sequences**](./) / [OTA Updates](#)

# OTA Updates

The Sequencer relies exclusively on `state` messages (to track phase and version changes) and `events/system` telemetry (to track execution milestones via log categories).

### **Category 1: Reference-Based Delivery (`url`)**

**Test 1: Standard URL Delivery (Happy Path)**

1. Sequencer publishes a `config` message with a valid `url` and the correct `sha256` hash.
2. Sequencer validates the device publishes a `state` message transitioning to `phase: apply`.
3. Sequencer validates the device publishes an `events/system` log with category `blobset.download.start`.
4. Sequencer validates the device publishes an `events/system` log with category `blobset.download.success`.
5. Sequencer validates the device publishes an `events/system` log with category `blobset.hash.verify`.
6. Sequencer validates the device publishes an `events/system` log with category `blobset.apply.success`.
7. Sequencer validates the device publishes a `state` message transitioning to `phase: final` with the `status` block omitted (null).
8. Sequencer validates the `system.software` block in the device `state` message reflects the newly updated version.

**Test 2: URL Network / Reachability Failure**

1. Sequencer publishes a `config` message with an unreachable/expired `url`.
2. Sequencer validates the device publishes a `state` message transitioning to `phase: apply`.
3. Sequencer validates the device publishes an `events/system` log with category `blobset.download.start`.
4. Sequencer validates the device publishes an `events/system` log with category `blobset.download.timeout` (or `blobset.download.forbidden` for 403 errors).
5. Sequencer validates the device safely times out and publishes a `state` message transitioning to `phase: final`.
6. Sequencer validates this final state contains a `status` block with a Level 500 `ERROR` (or appropriate transient retry error if limits are exhausted).

**Test 3: URL Cryptographic Hash Mismatch**

1. Sequencer publishes a `config` message with a valid `url` but an intentionally incorrect `sha256` hash.
2. Sequencer validates the device publishes a `state` message transitioning to `phase: apply`.
3. Sequencer validates the device publishes an `events/system` log with category `blobset.download.start`.
4. Sequencer validates the device publishes an `events/system` log with category `blobset.download.success`.
5. Sequencer validates the device publishes an `events/system` log with category `blobset.hash.verify`.
6. Sequencer validates the device publishes an `events/system` log with category `blobset.verify.hash_mismatch`.
7. Sequencer validates the device publishes a `state` message transitioning to `phase: final` featuring a Level 500 fatal `ERROR` in the status block.

**Test 4: Hardware / Dependency Mismatch (The Safety Check)**

1. Sequencer publishes a `config` message with a valid `url` and `sha256`, but the target bundle is explicitly incompatible with the hardware or existing modules.
2. Sequencer validates the device publishes a `state` message transitioning to `phase: apply`.
3. Sequencer validates the download and hash verification logs: `blobset.download.start`, `blobset.download.success`, and `blobset.hash.verify`.
4. Sequencer validates the device publishes an `events/system` log with category `blobset.verify.hardware_mismatch` or `system.software.dependency_conflict`.
5. Sequencer validates the device publishes a `state` message transitioning to `phase: final` featuring a Level 500 fatal `ERROR`.

---

### **Category 2: Inline Payload Delivery (`data`)**

**Test 5: Inline Data Delivery (Happy Path)**

1. Sequencer publishes a `config` message providing payload directly in the `data` field (base64) along with the correct `sha256` hash.
2. Sequencer validates the device publishes a `state` message transitioning to `phase: apply`.
3. Sequencer validates the device publishes an `events/system` log with category `blobset.hash.verify`.
4. Sequencer validates the device publishes an `events/system` log with category `blobset.apply.success`.
5. Sequencer validates the device publishes a `state` message transitioning to `phase: final` with the `status` block omitted.
6. Sequencer validates the device `state` reports a successful state update reflecting the applied data.

**Test 6: Inline Data Cryptographic Mismatch**

1. Sequencer publishes a `config` message with base64 `data` and an intentionally incorrect `sha256` hash.
2. Sequencer validates the device publishes a `state` message transitioning to `phase: apply`.
3. Sequencer validates the device publishes an `events/system` log with category `blobset.hash.verify`.
4. Sequencer validates the device publishes an `events/system` log with category `blobset.verify.hash_mismatch`.
5. Sequencer validates the device publishes a `state` message transitioning to `phase: final` featuring a Level 500 fatal `ERROR`.

**Test 7: Malformed Data Encoding**

1. Sequencer publishes a `config` message where the `data` string contains corrupted or invalid base64 characters.
2. Sequencer validates the device publishes a `state` message transitioning to `phase: apply`.
3. Sequencer validates the device publishes an `events/system` log with category `blobset.parse.error` (or similar decoding exception log).
4. Sequencer validates the device publishes a `state` message transitioning to `phase: final` featuring a Level 500 `ERROR` signifying a payload parsing failure.

---

### **Category 3: Lifecycle & Observability Protocol**

**Test 8: Strict Phase State Transitions**

1. Sequencer publishes a valid `blobset` `config` (either `url` or `data`).
2. Sequencer actively monitors the MQTT telemetry stream for state updates.
3. Sequencer strictly validates that a `state` message reporting `phase: apply` is received *before* any `state` message reporting `phase: final` is published.
4. Sequencer fails the test immediately if the device jumps straight to the `final` state without first acknowledging the intent via the `apply` phase.

**Test 9: Graceful Rollback Recognition**

1. Sequencer publishes a valid `blobset` `config`.
2. Sequencer validates the device publishes a `state` message transitioning to `phase: apply`.
3. While the device is actively in the `apply` phase, Sequencer publishes a new `config` message that completely removes the `blobset` block (simulating an orchestrator abort command).
4. Sequencer validates the device publishes an `events/system` log with category `blobset.apply.abort`.
5. Sequencer validates the device dynamically returns to its idle steady state (omitting the `blobset` block from its upstream `state` message) without executing a reboot or throwing a system crash.
