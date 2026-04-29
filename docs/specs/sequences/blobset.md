[**UDMI**](../../../) / [**Docs**](../../) / [**Specs**](../) / [**Sequences**](./) / [Blobset](#)

# Blobset Updates

The blobset feature allows for the delivery of binary large objects (blobs) or configuration data to a device via UDMI configuration messages. It orchestrates a strict two-phase deployment process to ensure device state remains synchronized with the cloud before disruptive actions (like a restart) occur.

## Two-Phase Deployment Pipeline

1. **Stage (Phase 1):** The payload is safely downloaded and verified without triggering disruptive actions.
2. **Activate (Phase 2):** The staged blob is activated (which may involve disruptive actions like a restart), but only after the device has successfully published its `FINAL` state to the cloud.

This ordering guarantees the cloud is aware of the successful update before the device potentially drops its connection during activation.

## Flow

1. **Receive Config:** The device receives a configuration update containing a blob in the `blobset.blobs` map with a specific generation and a phase of `final`.
2. **Apply Phase:** The device evaluates the blob against its current state. If the device's applied generation does not match the config generation, it transitions its state phase to `apply`.
3. **Fetch and Verify:** The device securely fetches the binary payload using the provided `url` and cryptographically verifies its integrity against the provided `sha256` hash.
4. **Stage:** The device performs Phase 1 (staging) by parsing, validating, or saving the data without disrupting core operations.
5. **Final State:** The device transitions the state phase to `final` and clears any previous error statuses. This state is immediately published to the cloud.
6. **Persist:** The newly applied generation string is persisted locally so it survives restarts.
7. **Activate:** The device performs Phase 2 (activation). This may include a process restart, service reload, or applying new firmware.

## Example Configuration

```json
{
  "blobset": {
    "blobs": {
      "firmware": {
        "phase": "final",
        "url": "https://example.com/firmware.bin",
        "sha256": "9c8423ac2e707a40c239fce4ce52b8c05ae8c32b163927b9350c97d0f64a8cf7",
        "generation": "2023-01-01T12:00:00Z"
      }
    }
  }
}
```
