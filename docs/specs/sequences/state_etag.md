[**UDMI**](../../../) / [**Docs**](../../) / [**Specs**](../) / [**Sequences**](./) / [State Etag](#)

# State Etag

The `state_etag` field is used in UDMI to prevent writeback race conditions. It ensures that cloud control commands (i.e. config messages setting a `set_value`) are only applied if the device's current pointset state matches the state the cloud observed when making its control decision.

This mechanism avoids scenarios where the cloud might send a configuration based on outdated state information (such as obsolete unit configurations), which could result in incorrect or potentially unsafe physical actuation.

## How `state_etag` works

The `state_etag` uniquely represents the configuration-critical aspects of a device's pointset state.
When the cloud sends a configuration update involving point writebacks, it includes the `state_etag` corresponding to the last state message it received from the device.

Upon receiving the configuration update:
1. The device calculates its own current `state_etag`.
2. The device compares its current `state_etag` to the `state_etag` provided in the incoming config.
3. If the etags **do not match**, it indicates the device state has changed since the cloud generated the config. The device will reject the writebacks and set the relevant point's `value_state` to `invalid` with an appropriate status message.
4. If the etags **match**, the device processes the writebacks and attempts to apply the `set_value`.

The device must re-calculate and publish a new `state_etag` in its state message whenever any of the contributing fields for any point change.

## Calculating `state_etag`

The `state_etag` calculation is fully deterministic, ensuring that any two systems calculating the etag for the exact same pointset state will yield the identical value.

The algorithm to calculate the `state_etag` is as follows:

1. **Construct a state dictionary**: Create a map of all managed points. For each point, the dictionary may contain up to three keys, included *only* if they have a non-null value:
   - `units`: The current operational units of the point.
   - `value_state`: The current enumeration indicating the writeback status (e.g., `applied`, `invalid`, `failure`).
   - `set_value`: The last known `set_value` requested for the point.

2. **Deterministic JSON Serialization**: Serialize the state dictionary to a JSON string. To ensure the resulting string is completely deterministic, it must be serialized with:
   - Lexicographical sorting of all object keys.
   - No whitespace characters (spaces, tabs, newlines) used as separators or for indentation. Specifically, separators must be exactly `,` and `:`.

3. **SHA-256 Hash**: Calculate the SHA-256 cryptographic hash of the UTF-8 encoded deterministic JSON string.

4. **Truncation**: The final `state_etag` is exactly the first 32 characters of the resulting hexadecimal hash representation.

### Example

Suppose a device manages two points, `fan_speed` and `temperature_sensor`.
The current state representation for calculation might look like this logically:

```json
{
  "fan_speed": {
    "set_value": 50,
    "units": "percent",
    "value_state": "applied"
  },
  "temperature_sensor": {
    "units": "Celsius"
  }
}
```

The deterministically serialized JSON string exactly as it will be hashed:
`{"fan_speed":{"set_value":50,"units":"percent","value_state":"applied"},"temperature_sensor":{"units":"Celsius"}}`

The resulting SHA-256 hash in hexadecimal:
`3796d17fb692eb18f972b9a7c9d7496cd712b7a9deee0e5a61b65ad57393de79`

The final `state_etag` value included in the UDMI state and config payloads (first 32 characters):
`3796d17fb692eb18f972b9a7c9d7496c`
