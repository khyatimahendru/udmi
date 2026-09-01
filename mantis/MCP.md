# UDMI Model Context Protocol (MCP) Specification

This document defines the Model Context Protocol (MCP) architecture for the UDMI ecosystem. All MCP server functionality, tool schemas, and JSON-RPC 2.0 dispatching are centralized in the top-level `mcp/` package (`mcp/server.py` and `mcp/session_manager.py`).

---

## 1. Design Philosophy: Composable Primitives over Monolithic Wrappers

Rather than defining narrow, single-purpose monolithic tools (such as separate tools for starting individual services or black-box triage), the UDMI MCP server provides **orthogonal, composable primitives** organized into four functional tiers:

```
UDMI MCP Tool Architecture
├── Tier 1: Session & Process Lifecycle (Tmux Process Management)
│   ├── ensure_test_setup         (Start/validate isolated stack & port block)
│   ├── start_session_process     (Launch any command into a named semantic window)
│   ├── get_test_logs             (Capture live console buffer from any window)
│   ├── list_test_windows         (List active semantic windows in a session)
│   ├── list_test_setups          (List active environments and port allocations)
│   └── terminate_test_setup      (Tear down session and clean runtime storage)
│
├── Tier 2: Live Protocol & Database Probing (Runtime State Inspection)
│   ├── query_database            (Execute read-only SQL/InfluxQL queries on active session DBs)
│   └── publish_mqtt_message      (Inject test packets into Mosquitto broker)
│
├── Tier 3: Specification & Site Model Grounding (Static Schema & Config)
│   ├── inspect_udmi_schema       (Retrieve JSON schema contracts from schema/)
│   ├── inspect_site_model        (Inspect device metadata and cloud IoT configurations)
│   └── patch_site_model          (Safely update metadata.json properties)
│
└── Tier 4: Diagnostics & Root Cause Analysis (Deterministic & Verified Triage)
    ├── get_test_timeline         (Extract deterministic event timestamps, transactions, cutoffs)
    ├── compare_test_runs         (Differential alignment between target and baseline runs)
    └── diagnose_test_failure     (End-to-end multi-stage diagnostic synthesis)
```

---

## 2. Server Configuration (`mcp_config.json`)

To register the UDMI MCP server with an external AI client (such as Gemini CLI, Claude Code, Cursor, or Windsurf), configure `mcp_config.json`:

```json
{
  "mcpServers": {
    "udmi": {
      "command": "bin/test_infra_mcp",
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

Alternatively, `bin/mantis --mcp` delegates directly to the same unified `mcp.server.main()` entry point.

---

## 3. Tool Definitions & JSON Schemas

### Tier 1: Session & Process Lifecycle

#### 3.1. `ensure_test_setup`
Provisions an isolated local UDMI stack inside a dedicated tmux session.

```json
{
  "name": "ensure_test_setup",
  "description": "Ensures that an isolated local UDMI test infrastructure stack (Mosquitto broker, UDMIS control plane, etcd, InfluxDB, PostgreSQL, and optional DUT) is running inside a tmux session, healthy, and ready for client traffic.",
  "parameters": {
    "type": "object",
    "required": ["test_id"],
    "properties": {
      "test_id": {
        "type": "string",
        "description": "Unique test run identifier (e.g. 'dev_run_1', 'suite_pointset')."
      },
      "site_model": {
        "type": "string",
        "description": "Path to the target site model directory.",
        "default": "sites/udmi_site_model"
      },
      "dut_device_id": {
        "type": "string",
        "description": "Optional device ID to automatically launch as an emulated Pubber DUT."
      },
      "dut_serial_no": {
        "type": "string",
        "description": "Optional serial number for the emulated DUT."
      },
      "exclude": {
        "type": "array",
        "items": {"type": "string"},
        "description": "List of canonical sub-services to exclude (e.g. ['udmis', 'influxdb'])."
      },
      "added": {
        "type": "array",
        "items": {"type": "string"},
        "description": "List of optional sub-services to add (e.g. ['validator', 'spotter'])."
      },
      "clean": {
        "type": "boolean",
        "description": "Whether to clean existing state before startup (default: true).",
        "default": true
      },
      "timeout_seconds": {
        "type": "integer",
        "description": "Maximum seconds to wait for stack readiness (default: 150).",
        "default": 150
      }
    }
  }
}
```

#### 3.2. `start_session_process`
Launches any command or test process inside a named semantic window of an active tmux session.

```json
{
  "name": "start_session_process",
  "description": "Launches a command or test process inside a named semantic window of an active UDMI session (e.g. launching sequencer tests, custom Pubber devices, or monitoring scripts).",
  "parameters": {
    "type": "object",
    "required": ["test_id", "window", "command"],
    "properties": {
      "test_id": {
        "type": "string",
        "description": "Identifier of the active test session."
      },
      "window": {
        "type": "string",
        "description": "Semantic window tag (e.g., 'sequencer', 'dut', 'validator', 'custom')."
      },
      "command": {
        "type": "string",
        "description": "Command line string to execute within the isolated session environment."
      }
    }
  }
}
```

#### 3.3. `get_test_logs`
Captures live console output from a named semantic tmux window.

```json
{
  "name": "get_test_logs",
  "description": "Captures live console output from a named semantic tmux window (e.g. 'main', 'dut', 'sequencer', 'butler', 'validator') for an active test session.",
  "parameters": {
    "type": "object",
    "required": ["test_id"],
    "properties": {
      "test_id": {
        "type": "string",
        "description": "Identifier of the test session."
      },
      "window": {
        "type": "string",
        "description": "Semantic window tag ('main', 'dut', 'sequencer', 'butler', 'validator').",
        "default": "main"
      },
      "lines": {
        "type": "integer",
        "description": "Number of recent lines to capture.",
        "default": 100
      }
    }
  }
}
```

#### 3.4. `list_test_windows`
Lists available semantic window tags for an active session.

```json
{
  "name": "list_test_windows",
  "description": "Lists the active semantic window tags for a running test session.",
  "parameters": {
    "type": "object",
    "required": ["test_id"],
    "properties": {
      "test_id": {
        "type": "string",
        "description": "Identifier of the active test session."
      }
    }
  }
}
```

#### 3.5. `list_test_setups`
Lists all active UDMI test environments and their assigned port mappings.

```json
{
  "name": "list_test_setups",
  "description": "Lists all active UDMI test sessions, port allocations, and running services.",
  "parameters": {
    "type": "object",
    "properties": {}
  }
}
```

#### 3.6. `terminate_test_setup`
Terminates a running tmux test session and purges instance runtime storage.

```json
{
  "name": "terminate_test_setup",
  "description": "Terminates the test infrastructure and tmux session associated with a test_id.",
  "parameters": {
    "type": "object",
    "required": ["test_id"],
    "properties": {
      "test_id": {
        "type": "string",
        "description": "Identifier of the test session to terminate."
      },
      "clean_workspace": {
        "type": "boolean",
        "description": "Whether to purge per-instance runtime storage (default: true).",
        "default": true
      }
    }
  }
}
```

---

### Tier 2: Live Protocol & Database Probing

#### 3.7. `query_database`
Executes safe read-only SQL or InfluxQL queries against the runtime databases of an active session.

```json
{
  "name": "query_database",
  "description": "Executes a read-only query against the InfluxDB or PostgreSQL instances of an active test session to inspect state records and telemetry written by Butler.",
  "parameters": {
    "type": "object",
    "required": ["test_id", "database_type", "query"],
    "properties": {
      "test_id": {
        "type": "string",
        "description": "Identifier of the active test session."
      },
      "database_type": {
        "type": "string",
        "enum": ["influx", "postgres"],
        "description": "Target database type."
      },
      "query": {
        "type": "string",
        "description": "SQL or InfluxQL query string (e.g. 'SELECT * FROM pointset LIMIT 5')."
      }
    }
  }
}
```

#### 3.8. `publish_mqtt_message`
Publishes an arbitrary test payload to an active session's Mosquitto broker.

```json
{
  "name": "publish_mqtt_message",
  "description": "Publishes a test message to an active session's Mosquitto MQTT broker.",
  "parameters": {
    "type": "object",
    "required": ["test_id", "topic", "payload"],
    "properties": {
      "test_id": {
        "type": "string",
        "description": "Identifier of the active test session."
      },
      "topic": {
        "type": "string",
        "description": "MQTT topic path (e.g., 'devices/AHU-1/config')."
      },
      "payload": {
        "type": "string",
        "description": "JSON payload string to publish."
      }
    }
  }
}
```

---

### Tier 3: Specification & Site Model Grounding

#### 3.9. `inspect_udmi_schema`
Retrieves authoritative JSON schema definitions for any UDMI message block.

```json
{
  "name": "inspect_udmi_schema",
  "description": "Retrieves the authoritative JSON schema definition for a specified UDMI message type.",
  "parameters": {
    "type": "object",
    "required": ["schema_name"],
    "properties": {
      "schema_name": {
        "type": "string",
        "description": "Name of the schema or message type (e.g. 'pointset', 'state_system', 'config_pointset')."
      },
      "sub_path": {
        "type": "string",
        "description": "Optional dot-delimited property sub-path to inspect specific object properties."
      }
    }
  }
}
```

#### 3.10. `inspect_site_model`
Inspects site configuration (`cloud_iot_config.json`) or device metadata (`metadata.json`).

```json
{
  "name": "inspect_site_model",
  "description": "Inspects site model configuration files and device metadata.",
  "parameters": {
    "type": "object",
    "required": ["site_model"],
    "properties": {
      "site_model": {
        "type": "string",
        "description": "Path to site model directory (e.g., 'sites/udmi_site_model')."
      },
      "device_id": {
        "type": "string",
        "description": "Optional device identifier to inspect specific device metadata."
      }
    }
  }
}
```

#### 3.11. `patch_site_model`
Safely updates or fixes JSON keys in a device `metadata.json` file.

```json
{
  "name": "patch_site_model",
  "description": "Updates or patches configuration keys in a device metadata.json file.",
  "parameters": {
    "type": "object",
    "required": ["site_model", "device_id", "patch_data"],
    "properties": {
      "site_model": {
        "type": "string",
        "description": "Path to site model directory."
      },
      "device_id": {
        "type": "string",
        "description": "Target device identifier."
      },
      "patch_data": {
        "type": "object",
        "description": "Key-value dictionary of fields to update in metadata.json."
      }
    }
  }
}
```

---

### Tier 4: Diagnostics & Root Cause Analysis

#### 3.12. `get_test_timeline`
Extracts raw chronological timestamps, transaction IDs (`RC:...`), and status transitions for a test run.

```json
{
  "name": "get_test_timeline",
  "description": "Extracts a structured chronological event timeline (timestamps, transactions, cutoff thresholds) from test logs.",
  "parameters": {
    "type": "object",
    "required": ["test_id", "device_id"],
    "properties": {
      "test_id": {
        "type": "string",
        "description": "Name of the test sequence (e.g., 'pointset_publish')."
      },
      "device_id": {
        "type": "string",
        "description": "Device identifier under test."
      },
      "run_dir": {
        "type": "string",
        "description": "Optional directory containing test run outputs."
      }
    }
  }
}
```

#### 3.13. `compare_test_runs`
Performs behavioral differential sequence alignment between a target run and a reference baseline.

```json
{
  "name": "compare_test_runs",
  "description": "Performs behavioral differential alignment between two test runs to isolate protocol state machine divergence.",
  "parameters": {
    "type": "object",
    "required": ["target_run"],
    "properties": {
      "target_run": {
        "type": "string",
        "description": "Path or identifier for target test run."
      },
      "baseline_run": {
        "type": "string",
        "description": "Path or commit hash for reference baseline run."
      }
    }
  }
}
```

#### 3.14. `diagnose_test_failure`
Performs complete multi-stage root-cause analysis on a failed test execution using the built-in adversarial critique loop.

```json
{
  "name": "diagnose_test_failure",
  "description": "Performs complete root-cause analysis on a failed test execution using the built-in adversarial critique loop.",
  "parameters": {
    "type": "object",
    "required": ["test_id", "device_id"],
    "properties": {
      "test_id": {
        "type": "string",
        "description": "Test sequence name (e.g., 'pointset_publish')."
      },
      "device_id": {
        "type": "string",
        "description": "Device identifier under test."
      },
      "site_model": {
        "type": "string",
        "description": "Site model directory path."
      },
      "run_dir": {
        "type": "string",
        "description": "Optional directory containing test run outputs."
      }
    }
  }
}
```
