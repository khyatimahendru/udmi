[**UDMI**](../../../) / [**Docs**](../../) / [**Specs**](../) / [**Sequences**](./) / [State Etag](#)

# State Etag Logic

## Overview
In UDMI, the `state_etag` is used to prevent writeback race conditions, where a cloud control command (config update) is applied based on an obsolete device state. It serves as a deterministic fingerprint of the device's current pointset configuration and status.

## Calculation
The `state_etag` is a SHA-256 hash derived from the JSON representation of the `pointset.points` states.
When generating the `state_etag`:
1. The device collects the current `get_state()` of all active points (which includes properties like `value_state`, `status`, and `units`).
2. This state map is serialized to JSON. To ensure determinism, the JSON serialization must use strictly sorted keys and remove any superfluous whitespace (e.g., using `separators=(',', ':')` in Python's `json.dumps`).
3. A SHA-256 digest of the resulting string is computed.
4. The first 32 characters of the hex digest are used as the `state_etag`.

## Flow
1. **Device Updates State**: Any time the state of any point changes (e.g., due to a local override or a config change), the device recalculates the `state_etag` and reports it in its `state` message.
2. **Cloud Receives State**: The cloud receives the new state and updates its internal representation.
3. **Cloud Issues Writeback**: When sending a writeback via a config update, the cloud includes the latest `state_etag` it is aware of.
4. **Device Validates config**: Upon receiving the config, the device compares the incoming `state_etag` against its locally calculated `state_etag`.
   - **Match**: The config is valid and the writeback is processed.
   - **Mismatch**: A race condition is detected. The device rejects the writeback, setting the `value_state` of the target points to `invalid` and supplying a status message indicating the `state_etag` mismatch.
