
## key_rotation_reconnect_failure_rollback (PREVIEW)

Validates automatic rollback upon key rotation reconnection failure.

1. Update config trigger key rotation with simulated reconnect failure
    * Add `blobset` = { "blobs": { "_iot_endpoint_credentials": { "phase": `final`, "generation": `blob generation`, "sha256": `blob data hash`, "url": `credentials data` } } }
1. Wait until system logs level `DEBUG` category `blobset.blob.receive`
1. Wait until system logs level `DEBUG` category `blobset.blob.fetch`
1. Wait until system logs level `NOTICE` category `blobset.blob.apply`
1. Wait for _iot_endpoint_credentials phase is FINAL
1. Check that _iot_endpoint_credentials state indicates rollback error

Test passed.
