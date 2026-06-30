# Discovery Node Technical Specification & System Architecture

This document provides a comprehensive functional and technical specification for **Discovery Node**, an edge service component of the Universal Device Management Interface (UDMI) framework. It contains all architectural details, configuration contracts, protocol interfaces, data schemas, family scanning behaviors, containerization details, and test suites required to build a functionally equivalent, drop-in replacement in any programming language.

---

## 1. Executive Overview & System Purpose

The **Discovery Node** is an edge-deployed micro-service designed to perform local network and protocol discovery for building automation, IoT networks, and IT infrastructure. It bridges local network devices with the cloud-based UDMI management plane.

### Core Responsibilities
1. **MQTT Telemetry & Control Bridge**: Maintains secure communication with an MQTT broker (GCP IoT Core / ClearBlade or Local UDMIS broker), subscribing to system configuration directives and publishing node state updates and discovery telemetry events.
2. **Dynamic Discovery Orchestration**: Processes runtime configuration updates to schedule, execute, cancel, or periodically repeat network discovery scans across enabled protocol families.
3. **Multi-Family Network Scanning**: Executes passive packet sniffing, active ICMP ping sweeps, port/service scanning (via Nmap), BACnet network Who-Is and object/property reads, and synthetic vendor metric generation.
4. **UDMI Schema Compliance**: Translates network scan results into standardized UDMI Discovery Event messages and maintains a compliant UDMI Device State tree.

---

## 2. System Architecture & Component Interactions

```
 +-----------------------------------------------------------------------------------+
 |                                 MQTT Broker                                       |
 |                      (GCP IoT / ClearBlade / Local UDMIS)                         |
 +-----------------------------------------------------------------------------------+
            ^ (State & Discovery Events)            | (Config Messages)
            |                                       v
 +-----------------------------------------------------------------------------------+
 |                                 Discovery Node                                    |
 |                                                                                   |
 |  +-----------------------+   Config   +----------------------------------------+  |
 |  |     MQTT Transport    | ---------> |             UDMI Core Engine           |  |
 |  |    (Client & Auth)    |            |  - State Management & Publishing       |  |
 |  +-----------------------+            |  - Config Routing & Handlers           |  |
 |                                       +----------------------------------------+  |
 |                                                           |                       |
 |                                            Config Sync &  | Hooks / Event         |
 |                                            Control Signals| Callbacks             |
 |                                                           v                       |
 |  +-----------------------------------------------------------------------------+  |
 |  |                         Discovery Controllers Base                          |  |
 |  |  - Scheduling Thread Engine (Generation calculation & Modular Repeat)       |  |
 |  |  - Lifecycle State Machine (PENDING -> ACTIVE -> STOPPED)                   |  |
 |  |  - Active Event Counter & Status Tracking                                   |  |
 |  +-----------------------------------------------------------------------------+  |
 |        |                        |                        |                |       |
 |        v                        v                        v                v       |
 |  +-----------+            +-----------+            +-----------+    +-----------+ |
 |  |  Vendor   |            |  BACnet   |            |   IPv4    |    |   Ether   | |
 |  | (Numbers) |            | Discovery |            | (Passive) |    |  (Active) | |
 |  +-----------+            +-----------+            +-----------+    +-----------+ |
 |                                 |                        |                |       |
 +---------------------------------|------------------------|----------------|-------+
                                   v                        v                v
                         [ BACnet IP Devices ]       [ Raw Network ]   [ ICMP / Nmap ]
```

### Execution & Threading Model
- **Main Thread**: Initializes local configuration, sets up logging, initializes the MQTT publisher, boots the UDMI core engine, starts the MQTT network client loop, and remains alive.
- **State Monitor Thread**: Runs continuously at a 1-second interval. Detects state tree changes via hashing, executes pre-publish hooks across active discovery modules (updating active event counters), and publishes updated state payloads over MQTT when changes occur.
- **Scheduler Threads**: Dedicated daemon thread created per active discovery family. Handles start/stop execution timing based on generation timestamps and configured intervals.
- **Worker / Scanner Threads**: Sub-threads or thread pools spawned by family controllers to execute async packet sniffing (Scapy), parallel ping workers, Nmap process management, or BACnet read pipelines.

---

## 3. Configuration & Authentication Contracts

The Discovery Node operates using two distinct configuration layers: **Local Boot Configuration** (file-based) and **Dynamic System Configuration** (MQTT-based).

### 3.1 Local Boot Configuration (`config.json`)

The local configuration file provides bootstrap credentials, broker network targets, and module activation flags.

#### Schema Structure
- `mqtt` (Object, Required):
  - `device_id` (String, Required): ID of the discovery gateway device.
  - `registry_id` (String, Required): UDMI registry identifier.
  - `project_id` (String, Required): Cloud project ID or local broker scope.
  - `region` (String, Required): Cloud region (e.g., `us-central1`).
  - `host` (String, Required): Broker hostname or IP.
  - `port` (Integer, Required): Broker port (typically `8883` for TLS).
  - `key_file` (String, Required): Path to private key file (RSA/PEM format).
  - `public_key_file` (String, Optional): Path to public key file.
  - `cert_file` (String, Optional): Path to client certificate file (for mTLS).
  - `ca_file` (String, Optional): Path to CA certificate file.
  - `algorithm` (String, Required): Key signature algorithm (e.g., `RS256`).
  - `authentication_mechanism` (String, Required): `jwt_gcp` or `udmi_local`.
- `configs_dir` (String, Optional): Directory containing overlay `.json` files. If specified, all `.json` files in this folder are read and recursively merged onto the base configuration.
- `udmi` (Object, Optional):
  - `discovery` (Object, Optional):
    - `ipv4` (Boolean): Enable/disable passive IPv4 network scanner.
    - `ether` (Boolean): Enable/disable active ethernet (ping/nmap) scanner.
    - `bacnet` (Boolean): Enable/disable BACnet IP scanner.
    - `vendor` (Boolean): Enable/disable synthetic number generator.
- `bacnet` (Object, Optional):
  - `ip` (String): Explicit IP address/subnet mask for binding BACnet interface.
- `ether` (Object, Optional):
  - `ping_concurrency` (Integer): Maximum concurrent ping execution workers (default: 4).
- `nmap` (Object, Optional):
  - `targets` (List of Strings): Target IP addresses or subnets.
  - `interface` (String): Network interface name for Nmap execution.
- `ip` (Object, Optional):
  - `subnet_filter` (String): Subnet CIDR filter for passive packet capture.

### 3.2 Authentication Modes

| Mode | Topic Prefix Pattern | MQTT Client ID Pattern | Username Format | Password / Secret Format | TLS Setup |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `jwt_gcp` | `/devices/{device_id}` | `projects/{project_id}/locations/{region}/registries/{registry_id}/devices/{device_id}` | `unused` | Signed RS256 JWT containing `iat` (now), `exp` (now + 60m), `aud` (`project_id`) | Server TLS using `ca_file` |
| `udmi_local` | `/r/{registry_id}/d/{device_id}` | `/r/{registry_id}/d/{device_id}` | `/r/{registry_id}/d/{device_id}` | First 8 hex characters of SHA-256 hash of the PKCS#8 private key binary | mTLS using `ca_file`, `key_file`, and `cert_file` |

---

## 4. MQTT Topics & Communication Protocol

### 4.1 Topic Definitions

Let `{prefix}` represent either `/devices/{device_id}` (GCP mode) or `/r/{registry_id}/d/{device_id}` (Local mode).

- **Config Topic (Subscribe)**: `{prefix}/config` (QoS 1)
- **State Topic (Publish)**: `{prefix}/state`
- **Discovery Events Topic (Publish)**: `{prefix}/events/discovery`
- **System Events Topic (Publish)**: `{prefix}/events/system`

### 4.2 Dynamic UDMI Config Specification (`{prefix}/config`)

The node processes runtime config payloads arriving on the config topic:

```json
{
  "timestamp": "2026-06-30T08:00:00Z",
  "discovery": {
    "families": {
      "<family_name>": {
        "generation": "2026-06-30T08:00:00Z",
        "scan_interval_sec": 60,
        "scan_duration_sec": 30,
        "depth": "refs",
        "addrs": ["192.168.12.1"]
      }
    }
  }
}
```

- Target `<family_name>` options: `vendor`, `bacnet`, `ipv4`, `ether`.
- If a family block is removed from `discovery.families`, discovery for that family must immediately terminate, and its state entry must be reset.
- If identical configuration is re-received, it must be ignored without interrupting ongoing scans.

---

## 5. Base Discovery Controller & Lifecycle State Machine

All discovery family implementations must derive from or adhere to the **Base Discovery Controller** lifecycle specification.

### 5.1 Lifecycle State Machine

```
   +---------------+
   |  INITIALIZED  |
   +---------------+
           |
           v (Config Received)
   +---------------+
   |   SCHEDULED   | <-------------------------------------+
   +---------------+                                       |
           |                                               |
           v (Timer Fired / Action Start)                  | (Repeat Interval Exists)
   +---------------+                                       |
   |   STARTING    | ---> [Publish Start Marker: event_no = 0]
   +---------------+                                       |
           |                                               |
           v                                               |
   +---------------+                                       |
   |    STARTED    | ---> [Publish Events: event_no = 1..N]
   +---------------+                                       |
           |                                               |
           v (Duration Expired / Action Stop)              |
   +---------------+                                       |
   |  CANCELLING   | ---> [Publish Stop Marker: event_no = -(N+1)]
   +---------------+                                       |
           |                                               |
           v                                               |
   +---------------+                                       |
   |   CANCELLED   | --------------------------------------+
   +---------------+
```

### 5.2 UDMI State Phase Mapping

- `SCHEDULED` / `CANCELLING` -> UDMI Phase: `pending`
- `STARTED` -> UDMI Phase: `active`
- `CANCELLED` / `FINISHED` -> UDMI Phase: `stopped`
- Any uncaught error -> Internal State: `ERROR`, UDMI Status Level: `500`, Category: `discovery.error`

### 5.3 Event Counter & Marker Contract

Each scan cycle maintains a 1-based `count_events` counter:
- **Start Marker Event**: Published upon entering `STARTING` phase. Set `event_no = 0`.
- **Scan Discovery Events**: Published as targets are discovered. Increment counter per event and set `event_no = count_events` (1, 2, 3...).
- **Stop Marker Event**: Published upon entering `CANCELLING` phase. Set `event_no = -(count_events + 1)` (e.g., if 5 events were published, stop marker `event_no` is `-6`).

### 5.4 Generation & Schedule Calculation Algorithm

1. **Generation Validation**: Parse generation timestamp string into UTC datetime. Calculate time delta `t_delta = generation - now`.
2. **Tolerance Check**: A threshold constant `MAX_THRESHOLD_GENERATION` (set to `-10` seconds) determines whether past timestamps are acceptable.
3. **Past Generation with Interval**: If `t_delta < -10s` and `scan_interval_sec` is provided:
   - Calculate elapsed cycles: `cycles_elapsed, seconds_into_cycle = divmod(|t_delta|, scan_interval_sec)`.
   - Calculate cycle modifier: `modifier = 1` if `seconds_into_cycle > 10s` else `0`.
   - Next generation timestamp = `generation + (scan_interval_sec * (cycles_elapsed + modifier))`.
4. **Indefinite Execution**: If `scan_duration_sec` is not set or set to `0`, the scan runs continuously until cancelled.

---

## 6. Discovery Family Specifications

### 6.1 Vendor Family (`vendor`)
- **Purpose**: Diagnostic sequential number generator.
- **Family String**: `vendor`
- **Behavior**: Iterates over a sequence of numbers (either an explicit comma-separated list specified in `range` or infinite sequence starting at `1`). Emits one discovery event every second with `addr` set to the string representation of the current number.

### 6.2 BACnet Family (`bacnet`)
- **Purpose**: BACnet IP network scanning and object/property discovery.
- **Family String**: `bacnet`
- **Device ID**: `4194300` (Local virtual client device ID). Model Name: `DiscoveryNode`.
- **Scan Modes**:
  - **Global Broadcast Scan**: Used when `addrs` is null/empty. Sends BACnet `Who-Is` broadcast message across the local subnet. Accumulates discovered device IDs and IP addresses.
  - **Targeted Address Scan**: Used when `addrs` contains explicit IP targets. Dispatches concurrent thread pool workers (max workers: 3) to execute `ReadProperty` requests for object identifier (`device 4194303 objectIdentifier`) against target IPs.
- **Depth Levels**:
  - **Basic / Existence**: Emits `addr` = `<BACnet Device ID>` and maps IP address into `families.ipv4.addr`.
  - **`system`**: Executes `ReadPropertyMultiple` for `objectName`, `vendorName`, `firmwareRevision`, `modelName`, `serialNumber`, `description`, `location`, `applicationSoftwareVersion`. Populates `system.serial_no`, `system.hardware.make`, `system.hardware.model`, and `system.ancillary` dictionary.
  - **`refs`**: Enumerates all BACnet objects (`AI`, `AO`, `AV`, `BI`, `BO`, `BV`, `LP`, `MSI`, `MSO`, `MSV`, `CSV`). Maps each object to a `DiscoveryPoint` structure containing point name, description, present value, object type, units, and possible state values. Key format: `<Acronym>:<InstanceNumber>` (e.g., `AI:1`).
- **Scan Completion**: Concludes when device count remains unchanged for 300 seconds (silence threshold) or upon duration expiry.

### 6.3 IPv4 Passive Family (`ipv4`)
- **Purpose**: Non-intrusive passive network packet sniffing.
- **Family String**: `ipv4`
- **Packet Sniffing Engine**: Uses raw socket packet capture (Scapy filter layer: Ether, IP, ICMP, UDP).
- **BPF Filter Rules**:
  - Default: Private IPv4 range filter:
    `ip and (src net 10.0.0.0/8 or src net 172.16.0.0/12 or src net 192.168.0.0/16 or src net 100.64.0.0/10) and (dst net 10.0.0.0/8 or dst net 172.16.0.0/12 or dst net 192.168.0.0/16 or dst net 100.64.0.0/10)`
  - Custom Subnet Filter: Synthesizes BPF filter matching network address, explicitly excluding subnet network address, broadcast address, gateway address, and local node host IP.
- **Packet Processing**:
  - Inspects incoming packet source IP and MAC address.
  - Inspects UDP port `47808` (BACnet traffic) for BVLC header markers (`0x81`) and APDU `I-Am` service choice bytes (`0x10 0x00 0xC4`) to log potential BACnet instance numbers.
  - Performs reverse DNS lookup (`gethostbyaddr`) for discovered IP addresses.
- **Publish Cycle**: Queues new unique device records (`addr`, `mac`, `hostname`) and publishes discovery events every 5 seconds.

### 6.4 Ether Active Family (`ether`)
- **Purpose**: Active ICMP ping sweeps and Nmap port/service scanning.
- **Family String**: `ether`
- **Depth Selection**:
  - `depth: "ping"` -> Executes ICMP Ping Dispatcher.
  - `depth: "ports"` or `"services"` -> Executes Nmap Engine.
- **Ping Engine**:
  - Worker pool with configurable concurrency (default: 4 threads).
  - Invokes system binary `/usr/bin/ping -c 1 -W 2 <target_ip>`.
  - On ping response, emits a discovery event with `families.ipv4.addr = target_ip`.
- **Nmap Engine**:
  - Executes subprocess `/usr/bin/nmap` with flags:
    - Base flags: `-p- -T3 -oX nmaplocalhost.xml --stats-every 5s <addrs>`
    - Extra flags for `depth: "services"`: `--script banner -A`
  - Periodically checks subprocess status with 1-second timeout to allow fast cancellation if stop signal is received.
  - XML Parser: Parses output XML to build `NmapHost` and `NmapPort` records.
  - Maps port details into `refs.<port_number>.adjunct` object (containing `port_number`, `protocol`, `state`, `service`, `version`, `product`, `banner`). Emits discovery event per discovered host.

---

## 7. Data Schemas & Payload Structures

### 7.1 UDMI State Schema (`{prefix}/state`)

Published over MQTT whenever node state or discovery family status updates.

```json
{
  "timestamp": "2026-06-30T08:55:00Z",
  "version": "1.5.1",
  "system": {
    "last_config": "2026-06-30T08:00:00Z",
    "software": {
      "version": "1.5.1"
    },
    "hardware": {
      "make": "unknown",
      "model": "unknown"
    },
    "operation": {
      "operational": true
    },
    "serial_no": "unknown",
    "status": null
  },
  "localnet": {
    "families": {}
  },
  "discovery": {
    "families": {
      "bacnet": {
        "generation": "2026-06-30T08:00:00Z",
        "phase": "active",
        "active_count": 3,
        "status": null
      }
    }
  }
}
```

### 7.2 UDMI Discovery Event Schema (`{prefix}/events/discovery`)

Published per discovered entity, as well as for start (`event_no = 0`) and stop (`event_no < 0`) markers.

```json
{
  "timestamp": "2026-06-30T08:55:05Z",
  "version": "1.5.1",
  "generation": "2026-06-30T08:00:00Z",
  "family": "bacnet",
  "addr": "1001",
  "event_no": 1,
  "families": {
    "ipv4": {
      "addr": "192.168.12.1"
    }
  },
  "system": {
    "hardware": {
      "make": "Trane",
      "model": "BCU"
    },
    "software": {
      "firmware": "v4.1"
    },
    "serial_no": "SN-98765",
    "ancillary": {
      "description": "Main AHU Controller",
      "location": "Basement Mechanical Room",
      "name": "AHU-1"
    }
  },
  "refs": {
    "AI:1": {
      "name": "SupplyAirTemp",
      "description": "Supply Air Temperature Sensor",
      "type": "analogInput",
      "units": "degreesFahrenheit",
      "ancillary": {
        "present_value": 72.5
      }
    }
  }
}
```

### 7.3 Schema Sanitization Rules
Before serializing state or discovery events to JSON:
1. Null fields must be purged.
2. Empty dictionaries `{}` and empty strings/structures must be recursively pruned (up to 3 depth passes).

---

## 8. Containerization & System Integration Details

### 8.1 Container Environment Types

Discovery Node utilizes two distinct categories of container images for application execution and binary compilation:

#### 1. Runtime Application Container Image (`Dockerfile`)
- **Base OS**: `debian:12-slim` (Debian 12 Bookworm).
- **Build Stage**: Installs `python3-venv`, `gcc`, `libpython3-dev`, creates `/venv` virtual environment, and installs Python requirements (`cryptography`, `BAC0`, `bacpypes`, `scapy`, `paho-mqtt`, `pyjwt`, `pytest`, `numpy`).
- **Runtime Stage**: Copies `/venv` and `/app` into a slim `debian:12-slim` image equipped with runtime system tools (`python3`, `coreutils`, `nmap`, `iputils-ping`).
- **Entrypoint**: `/venv/bin/python3 main.py --config_file=/tmp/discoverynode_config.json`

#### 2. Binary Build Environment Container Images (`buildenvs/`)
To support compiling standalone self-contained binaries via `bin/build_binary` across target host operating systems with varying `glibc` toolchain versions, two dedicated build environment Docker images are maintained:
- **Debian 11 Build Image (`buildenvs/debian11.Dockerfile`)**:
  - Base OS: `debian:11` (Debian 11 Bullseye).
  - Environment: Compiles OpenSSL `1.1.1g` and Python `3.12.8` from source, installs `pyinstaller`, and sets up a build toolchain for modern Debian/GCP environments.
- **Ubuntu 16 Build Image (`buildenvs/ubuntu16.Dockerfile`)**:
  - Base OS: `ubuntu:16.04` (Ubuntu 16.04 LTS Xenial Xerus).
  - Environment: Compiles OpenSSL `1.1.1g` and Python `3.12.8` from source, installs `pyinstaller`, and provides backwards compatibility for legacy Linux kernel / `glibc` deployments.

### 8.2 System Linux Capabilities
Because passive sniffing (Scapy) and raw packet generation (Ping / Nmap) interact directly with network interfaces, the host runtime or Docker container must be granted system capabilities:
- `CAP_NET_RAW`: Required for raw socket binding, ICMP pings, and packet sniffing.
- `CAP_NET_ADMIN`: Required for interface promiscuous mode configuration and network status checks.

### 8.3 Systemd Service Daemon (`udmi_discovery.service`)

The daemon setup script installs the node as an always-on systemd service:

- **Service User**: `udmi_discovery`
- **Library Path**: `/usr/local/lib/udmi_discovery`
- **Config Path**: `/etc/udmi_discovery/config.json`
- **Certificates Path**: `/etc/udmi_discovery/certs/`
- **Unit File Directives**:
  - `ExecStart=/usr/local/lib/udmi_discovery/venv/bin/python3 /usr/local/lib/udmi_discovery/src/main.py --config_file=/etc/udmi_discovery/config.json`
  - `Restart=always`, `RestartSec=30s`
  - `Environment=PYTHONUNBUFFERED=1`
  - `CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN`
  - `AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN`

### 8.4 Standalone Executable Packaging (`bin/build_binary`)
The standalone single-file binary is generated by running `bin/build_binary <BUILD_ENV_IMAGE>`, which mounts `/src` into a selected build environment container (`debian11` or `ubuntu16`), installs dependencies, runs PyInstaller (`pyinstaller --onefile --hidden-import udmi main.py`), and outputs the executable binary to `dist/discoverynode`.

---

## 9. Testing & Verification Infrastructure

The Discovery Node test suite comprises three distinct testing tiers:

```
                  +-----------------------------------+
                  |      Integration Test Suite       |
                  |  - Docker network & BACnet container
                  |  - Full E2E message pipeline check
                  +-----------------------------------+
                                    |
                  +-----------------------------------+
                  |         Unit Test Suite           |
                  |  - Controller scheduler logic     |
                  |  - Generation & interval math     |
                  |  - Local config merge tests       |
                  |  - Nmap XML parser tests          |
                  +-----------------------------------+
```

### 9.1 Unit Testing (`testing/unit/unit_tests.sh`)
- **Execution Command**: `pytest --capture=no --ignore=tests/test_integration.py tests`
- **Key Test Cases**:
  - `test_number_discovery_start_and_stop`: Verifies correct start/stop sequence, Phase transition (`active` -> `stopped`), and marker payload output (`0` start marker, `1..N` events, negative stop marker).
  - `test_event_counts`: Verifies `active_count` tracking in state updates.
  - `test_generation_scheduling`: Parametrized test verifying timing calculations for past generations, interval math, and threshold tolerance.
  - `test_generation_is_incremented`: Verifies generation timestamp updates across repeated scan cycles.
  - `test_chain`: Verifies mode switching between ping and nmap when `depth` config changes.
  - `test_local_config`: Tests recursive dictionary merging of base configs with overlay files.
  - `test_nmap_result_reader`: Tests XML output parsing for Nmap port/service/banner extraction.

### 9.2 Integration Testing (`testing/integration/integration_test.sh`)
- **Infrastructure**:
  - Creates an isolated Docker bridge network (`discovery-integration`, subnet `192.168.12.0/24`).
  - Spawns mock BACnet device container (`test-bacnet-device`, IP `192.168.12.1`, BACnet ID `1`).
  - Runs integration test runner (`test_integration.py`) inside the `test-discovery_node` container connected to the same network.
- **Integration Scenarios**:
  - `test_bacnet_system`: Triggers BACnet discovery with `depth: "system"`. Verifies discovery of BACnet device ID `1` without points.
  - `test_bacnet_refs`: Triggers BACnet discovery with `depth: "refs"`. Verifies discovery of device ID `1` and populates `refs` point dictionary.
  - `test_nmap`: Triggers active ether discovery with `depth: "services"` targeting `192.168.12.1/24`. Verifies Nmap identification of SSH service banner (`OpenSSH`) on port 22.

---

## 10. Drop-in Replacement Requirements Checklist

An agent or engineer building a new implementation of Discovery Node (in Go, Rust, Java, C++, etc.) must fulfill the following functional contracts for complete compatibility:

1. **CLI & Config Arguments**: Accept `--config_file=<path>` argument to read boot configuration.
2. **Dynamic Overlay Merging**: Support reading `configs_dir` and recursively merging all `.json` files over the base configuration.
3. **MQTT Protocol Standards**:
   - Support both `jwt_gcp` (JWT password auth) and `udmi_local` (SHA256 hash of PKCS#8 key password auth + mTLS).
   - Subscribe to `{prefix}/config` and handle JSON config dispatching.
   - Publish `{prefix}/state` updates whenever state changes or pre-publish hooks execute.
4. **State Machine & Timing Engine**:
   - Implement generation timestamp schedule calculation with past-timestamp interval modular arithmetic and `-10` second tolerance.
   - Maintain UDMI state phases (`pending`, `active`, `stopped`) and error statuses.
   - Emit start markers (`event_no = 0`) and stop markers (`event_no = -(N+1)`).
5. **Scanner Implementations**:
   - **`vendor`**: Sequential numeric string generator.
   - **`bacnet`**: BACnet Who-Is broadcast & targeted IP scanning; `system` property read; `refs` object/point enumeration.
   - **`ipv4`**: Passive raw socket packet capture filtering private subnets; BVLC packet inspection; reverse DNS resolution.
   - **`ether`**: Parallel ICMP ping dispatcher; Nmap subprocess/library execution parsing open ports, services, banners, and mapping into `refs`.
6. **Payload Sanitization**: Purge null values and empty dictionary structures before serializing state and event payloads to JSON.
7. **System Privileges**: Ensure binary or container is configured with `CAP_NET_RAW` and `CAP_NET_ADMIN` privileges.
