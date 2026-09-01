---
name: component-guide
description: Comprehensive reference for UDMI component architecture, data envelopes, state machine processing, and backend bridging.
---

# UDMI Component Architecture Guide

## 1. Core System Components

* **Pubber (Device Emulator)**:
  Java-based reference IoT client. Implements UDMI device protocol, simulating pointsets, alarms, discoveries, system status, and config parsing.
* **Mosquitto MQTT Broker**:
  Central message transport routing packets between devices, gateway bridges, and backend control services.
* **UDMIS (UDMI Services Backend)**:
  Core Java processing engine consisting of:
  * `StateProcessor`: Validates, shards, and aggregates device state updates.
  * `ReflectProcessor`: Handles cloud-to-device configuration transactions and reflect queries.
* **Butler**:
  Message router and database synchronization bridge. Records telemetry streams into InfluxDB and device state histories into PostgreSQL.
* **Validator & Sequencer**:
  * `Validator`: Real-time telemetry validation daemon verifying schema compliance.
  * `Sequencer`: Automated end-to-end integration test runner validating protocol behavior across defined test sequences.

## 2. Message Channels & Envelope Structure
All messages flow across standardized MQTT topics:
* `devices/<device_id>/events/<subfolder>`: Telemetry events (e.g., `events/pointset`, `events/system`, `events/discovery`).
* `devices/<device_id>/state`: Device reported operational state.
* `devices/<device_id>/config`: Cloud-to-device target configuration.
