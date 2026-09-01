---
name: log-analysis
description: Factual reference for distributed log tracing, transaction correlation, timestamp cutoff detection, and log stream analysis in UDMI.
---

# UDMI Distributed Log Analysis Guide

## 1. Log Streams & Source Files
In the UDMI ecosystem, diagnostic logs are generated across multiple decoupled services:

* **`sequence.log`**: Test sequencer execution log. Contains test step transitions, config updates, expected state wait loops, and pass/fail assertions.
* **`pubber.log` / `device_system.log`**: Device-side emulation log. Records received config packets, published telemetry events, and state updates.
* **`udmis.log`**: UDMIS backend processor log. Tracks message ingestion, validation, state sharding (`StateProcessor`), and reflector transactions (`ReflectProcessor`).
* **`validator.log`**: Schema validation daemon log. Records JSON schema compliance errors and point-level validation warnings.

## 2. Distributed Tracing by Transaction ID (`RC:...`)
Configuration updates sent by the sequencer or cloud backend include a tracking ID formatted as `RC:<hash>.<sequence_num>` (e.g., `RC:9a6ddf.00000134`).

1. **Dispatch**: Sequencer sends config with transaction ID $\rightarrow$ `Dispatched config RC:9a6ddf.00000134`.
2. **Delivery**: Mosquitto delivers message to Pubber or physical device.
3. **Application**: Device processes configuration update.
4. **State Echo**: Device includes the acknowledged transaction ID in its reported state (`state.system.last_config = RC:9a6ddf.00000134`).
5. **Sequencer Confirmation**: Sequencer matches the reported state transaction ID with its dispatched update to mark the test stage as complete.

## 3. Timestamp Cutoff Thresholds & Stale State Rejections
The sequencer enforces strict timestamp cutoffs to ensure that device state updates reflect fresh transitions rather than cached past messages:

* When a test begins or enters a new stage, the sequencer records a **cutoff timestamp** (e.g. `Cutoff set: 2026-08-26T12:45:08Z`).
* Any incoming device state message with `state.timestamp < cutoff` is rejected with `ignoring stale state update`.
* If the device continues to send stale timestamps or fails to publish an updated state message within the stage timeout (default 120s), the sequencer fails with a state synchronization timeout.
