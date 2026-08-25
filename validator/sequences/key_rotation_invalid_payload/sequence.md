
## key_rotation_invalid_payload (PREVIEW)

Validates rejection of invalid payload during key rotation.

1. Update config trigger invalid key rotation payload
    * Add `blobset` = { "blobs": { "_iot_endpoint_credentials": { "phase": `final`, "generation": `blob generation`, "sha256": `blob data hash`, "url": `credentials data` } } }
1. Wait until system logs level `DEBUG` category `blobset.blob.receive`
1. Wait until system logs level `DEBUG` category `blobset.blob.fetch`
1. Wait until system logs level `ERROR` category `blobset.blob.parse`
1. Wait for _iot_endpoint_credentials phase is FINAL
1. Check that _iot_endpoint_credentials state indicates error

Test passed.
