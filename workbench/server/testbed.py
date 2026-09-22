"""Testbed infrastructure and Pubber emulator manager for UDMI Workbench (Layer 4).

Manages local substrate services (`bin/udmi start/stop/restart`) and simulated
device emulators (`bin/pubber`) in unprivileged user-space mode (`//mqtt/localhost:18833`).
Provides non-blocking health probing and structured service log tailing.
"""

import os
import re
import signal
import socket
import subprocess
import threading
import time
from typing import Any, Dict, Optional

from workbench.server import discovery
from workbench.server.logger import SERVER_LOGGER


DEFAULT_PROJECT_SPEC = "//mqtt/localhost:18833"
DEFAULT_MQTT_PORT = 18833
DEFAULT_ETCD_PORT = 2379
# The privileged MQTT port the substrate treats as "not isolated mode"; see
# the isolated-mode block in `etc/shell_common.sh`.
DEFAULT_MQTT_BROKER_PORT = 8883

# Anchored command-line patterns for the two components with no health port.
# These are matched against the whole command line, so they begin at its start:
# an unanchored fragment matches any process that merely mentions the path.
#: `bin/pubber`, optionally under the `/bin/bash -e` wrapper the script uses.
PUBBER_PROCESS_PATTERN = r"^(/[^ ]*/bash +-e +)?[^ ]*/bin/pubber( |$)"
#: The UDMIS pod, launched as a jar or via `bin/`-prefixed wrappers.
UDMIS_PROCESS_PATTERN = r"^[^ ]*(java|/bash)[^ ]* .*udmis[^ ]*\.jar( |$)|^[^ ]*/bin/(start_)?udmis( |$)"


def check_tcp_port(host: str, port: int, timeout: float = 0.4) -> bool:
    """Non-blocking TCP socket health check."""
    if not port or port <= 0:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def is_pid_alive(pid: Optional[int]) -> bool:
    """Returns True if the process exists and is alive."""
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _self_lineage() -> set:
    """This process and its ancestors.

    `pgrep` omits itself but not the shell that invoked us, nor the gateway
    process, either of which may carry a service path in its command line.
    """
    lineage, pid = set(), os.getpid()
    while pid and pid > 1 and pid not in lineage:
        lineage.add(pid)
        try:
            with open(f"/proc/{pid}/status", "r") as fh:
                for line in fh:
                    if line.startswith("PPid:"):
                        pid = int(line.split()[1])
                        break
                else:
                    break
        except (OSError, ValueError):
            break
    return lineage


def find_processes(pattern: str) -> list:
    """PIDs whose full command line matches `pattern`, excluding our own tree.

    `pattern` is an extended regular expression matched against the whole
    command line, so callers must anchor it. An unanchored fragment matches
    any process that merely mentions the path -- a `tail` of a log, an editor,
    another operator's shell -- and reporting a service UP on that basis is
    how a dead emulator comes to look healthy.
    """
    try:
        res = subprocess.run(
            ["pgrep", "-f", pattern],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2.0,
        )
    except Exception:
        return []
    if res.returncode != 0:
        return []
    mine = _self_lineage()
    pids = []
    for token in res.stdout.split():
        try:
            pid = int(token)
        except ValueError:
            continue
        if pid not in mine:
            pids.append(pid)
    return pids


def is_process_running(pattern: str) -> bool:
    """True when some process outside our own tree matches `pattern`."""
    return bool(find_processes(pattern))


def extract_port_from_spec(spec: str, default: int = DEFAULT_MQTT_PORT) -> int:
    """Extracts explicit port from project specification (e.g. //mqtt/localhost:18833)."""
    if not spec:
        return default
    match = re.search(r":(\d+)(?:/|$)", spec)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return default


def derive_etcd_port(mqtt_port: int) -> int:
    """Returns the etcd client port the substrate binds for a given MQTT port.

    Mirrors the canonical isolated-mode offset in `etc/shell_common.sh` (and
    `etc/tmux_common.sh`): any MQTT port other than the privileged default 8883
    selects user-space ports at MQTT_PORT+1 (etcd), +2 (influx), +3 (postgres).
    The privileged default keeps etcd on its own well-known port.
    """
    if mqtt_port and mqtt_port != DEFAULT_MQTT_BROKER_PORT:
        return mqtt_port + 1
    return DEFAULT_ETCD_PORT


class TestbedError(Exception):
    """Raised when a testbed operation fails validation or execution."""


class TestbedManager:
    """Controls local UDMI testbed substrate and Pubber lifecycle."""

    def __init__(self, udmi_root: str):
        self.udmi_root = os.path.abspath(udmi_root)
        self.out_dir = os.path.join(self.udmi_root, "out")
        os.makedirs(self.out_dir, exist_ok=True)

        self._lock = threading.Lock()
        self.active_site_model: Optional[str] = None
        self.active_project_spec: str = DEFAULT_PROJECT_SPEC
        self.mqtt_port: int = DEFAULT_MQTT_PORT
        self.etcd_port: int = derive_etcd_port(DEFAULT_MQTT_PORT)

        self.setup_process: Optional[subprocess.Popen] = None
        self.setup_log_path = os.path.join(self.out_dir, "testbed_setup.log")
        self.is_starting = False
        self.start_time: Optional[float] = None
        self.last_error: Optional[str] = None

        self.pubber_process: Optional[subprocess.Popen] = None
        self.pubber_info: Dict[str, Any] = {}
        self.pubber_log_path = os.path.join(self.out_dir, "pubber.log")

    def _resolve_site_model(self, site_model: str) -> str:
        """Resolves site model path and validates cloud_iot_config.json."""
        if not site_model:
            raise TestbedError("Missing required field: 'site_model'")
        abs_path = discovery.resolve_site_model(self.udmi_root, site_model)
        config_path = os.path.join(abs_path, "cloud_iot_config.json")
        if not os.path.isfile(config_path):
            raise TestbedError(f"Site model missing cloud_iot_config.json at {abs_path}")
        return abs_path

    def start(
        self,
        site_model: str,
        project_spec: str = DEFAULT_PROJECT_SPEC,
        clean: bool = False,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Launches local UDMI infrastructure services via bin/udmi start."""
        with self._lock:
            abs_site_model = self._resolve_site_model(site_model)
            spec = (project_spec or DEFAULT_PROJECT_SPEC).strip()
            self.mqtt_port = extract_port_from_spec(spec, DEFAULT_MQTT_PORT)
            self.etcd_port = derive_etcd_port(self.mqtt_port)
            self.active_site_model = site_model
            self.active_project_spec = spec
            self.is_starting = True
            self.start_time = time.time()
            self.last_error = None

            SERVER_LOGGER.info(
                "TestbedManager",
                "testbed.start",
                correlation_id=correlation_id,
                layer="GATEWAY",
                details={
                    "site_model": site_model,
                    "project_spec": spec,
                    "mqtt_port": self.mqtt_port,
                    "clean": clean,
                },
            )

            # Clean previous log
            try:
                with open(self.setup_log_path, "w") as f:
                    f.write(f"=== Starting UDMI Local Infrastructure ({spec}) ===\n")
            except Exception:
                pass

            def _run():
                try:
                    env = dict(os.environ)
                    env["UDMI_NO_SUDO"] = "true"
                    env["MQTT_PORT"] = str(self.mqtt_port)

                    if clean:
                        subprocess.run(
                            [os.path.join(self.udmi_root, "bin", "udmi"), "clean"],
                            cwd=self.udmi_root,
                            env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=30.0,
                        )

                    cmd = [
                        os.path.join(self.udmi_root, "bin", "udmi"),
                        "start",
                        abs_site_model,
                        spec,
                    ]
                    with open(self.setup_log_path, "a") as log_file:
                        proc = subprocess.Popen(
                            cmd,
                            cwd=self.udmi_root,
                            env=env,
                            stdout=log_file,
                            stderr=subprocess.STDOUT,
                            start_new_session=True,
                        )
                        self.setup_process = proc
                        proc.wait(timeout=120.0)
                except Exception as e:
                    self.last_error = str(e)
                    SERVER_LOGGER.error(
                        "TestbedManager",
                        "testbed.start.error",
                        error=e,
                        correlation_id=correlation_id,
                        layer="GATEWAY",
                    )
                finally:
                    self.is_starting = False

            thread = threading.Thread(target=_run, daemon=True)
            thread.start()

            return {
                "status": "INITIALIZING",
                "site_model": site_model,
                "project_spec": spec,
                "mqtt_port": self.mqtt_port,
                "message": "Local testbed starting in user-space isolated mode",
            }

    def stop(self, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Stops all local UDMI infrastructure and any running Pubber instance."""
        with self._lock:
            SERVER_LOGGER.info(
                "TestbedManager",
                "testbed.stop",
                correlation_id=correlation_id,
                layer="GATEWAY",
            )
            # 1. Stop pubber if running
            self._stop_pubber_internal()

            # 2. Stop local services
            env = dict(os.environ)
            env["UDMI_NO_SUDO"] = "true"
            try:
                subprocess.run(
                    [os.path.join(self.udmi_root, "bin", "udmi"), "stop"],
                    cwd=self.udmi_root,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30.0,
                )
            except Exception as e:
                SERVER_LOGGER.warn(
                    "TestbedManager",
                    "testbed.stop.warning",
                    details={"error": str(e)},
                    correlation_id=correlation_id,
                    layer="GATEWAY",
                )

            self.is_starting = False
            self.setup_process = None
            return {
                "status": "STOPPED",
                "message": "All local pipeline services stopped",
            }

    def restart(
        self,
        site_model: str,
        project_spec: str = DEFAULT_PROJECT_SPEC,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stops, cleans, and starts local testbed infrastructure."""
        self.stop(correlation_id=correlation_id)
        time.sleep(1.0)
        return self.start(
            site_model=site_model,
            project_spec=project_spec,
            clean=True,
            correlation_id=correlation_id,
        )

    def start_pubber(
        self,
        site_model: str,
        device_id: str,
        project_spec: str = DEFAULT_PROJECT_SPEC,
        serial_no: str = "1234",
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Starts a simulated Pubber device instance in background."""
        with self._lock:
            if not device_id:
                raise TestbedError("Missing required field: 'device_id'")
            abs_site_model = self._resolve_site_model(site_model)

            device_dir = os.path.join(abs_site_model, "devices", device_id)
            if not os.path.isdir(device_dir):
                raise TestbedError(f"Device directory not found: {device_dir}")

            spec = (project_spec or self.active_project_spec or DEFAULT_PROJECT_SPEC).strip()
            serial = (serial_no or "1234").strip()

            # Terminate existing pubber if running
            self._stop_pubber_internal()

            pubber_log_file = os.path.join(self.out_dir, f"pubber_{device_id}.log")
            self.pubber_log_path = pubber_log_file

            SERVER_LOGGER.info(
                "TestbedManager",
                "pubber.start",
                correlation_id=correlation_id,
                layer="GATEWAY",
                details={
                    "device_id": device_id,
                    "site_model": site_model,
                    "project_spec": spec,
                    "serial_no": serial,
                },
            )

            env = dict(os.environ)
            env["UDMI_NO_SUDO"] = "true"
            env["MQTT_PORT"] = str(extract_port_from_spec(spec, self.mqtt_port))

            cmd = [
                os.path.join(self.udmi_root, "bin", "pubber"),
                abs_site_model,
                spec,
                device_id,
                serial,
            ]

            log_f = open(pubber_log_file, "w")
            log_f.write(f"=== Starting Pubber for {device_id} ({spec}) ===\n")
            log_f.flush()

            proc = subprocess.Popen(
                cmd,
                cwd=self.udmi_root,
                env=env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self.pubber_process = proc
            self.pubber_info = {
                "device_id": device_id,
                "serial_no": serial,
                "site_model": site_model,
                "project_spec": spec,
                "pid": proc.pid,
                "started_at": time.time(),
            }

            return {
                "status": "RUNNING",
                "device_id": device_id,
                "serial_no": serial,
                "pid": proc.pid,
                "message": f"Pubber emulator started for {device_id}",
            }

    def _stop_pubber_internal(self) -> None:
        """Internal helper to terminate pubber process."""
        if self.pubber_process:
            try:
                if self.pubber_process.poll() is None:
                    self.pubber_process.terminate()
                    try:
                        self.pubber_process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        self.pubber_process.kill()
            except Exception:
                pass
            self.pubber_process = None

        # Clean any orphan pubber processes
        try:
            subprocess.run(
                ["pkill", "-f", "bin/pubber"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            )
        except Exception:
            pass

        self.pubber_info = {}

    def stop_pubber(
        self, device_id: Optional[str] = None, correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Stops the running Pubber device instance."""
        with self._lock:
            target_device = device_id or self.pubber_info.get("device_id")
            SERVER_LOGGER.info(
                "TestbedManager",
                "pubber.stop",
                correlation_id=correlation_id,
                layer="GATEWAY",
                details={"device_id": target_device},
            )
            self._stop_pubber_internal()
            return {
                "status": "STOPPED",
                "device_id": target_device,
                "message": "Pubber emulator stopped",
            }

    def get_status(self) -> Dict[str, Any]:
        """Executes non-blocking health checks against all local testbed components."""
        mqtt_port = self.mqtt_port
        mqtt_up = check_tcp_port("localhost", mqtt_port)

        pod_ready_path = os.path.join(self.udmi_root, "var", "pod_ready.txt")
        udmis_sentinel = os.path.isfile(pod_ready_path)
        # Anchored: the sentinel file alone survives a crash, and an unanchored
        # "udmis" matches this repository's own path in any command line.
        udmis_alive = is_process_running(UDMIS_PROCESS_PATTERN)
        udmis_up = udmis_sentinel and udmis_alive

        # The verdict must rest on the probe we report. A bare `pgrep etcd`
        # fallback would claim UP on the strength of a process that may be
        # bound to a different port, or wedged, or another checkout's.
        etcd_up = check_tcp_port("localhost", self.etcd_port)

        # The subprocess we started is the only first-hand evidence. Failing
        # that, an anchored command-line match covers an emulator an operator
        # launched by hand; a loose `bin/pubber` fragment used to match any
        # shell that merely named the path, so a dead emulator read as UP.
        pubber_dev = self.pubber_info.get("device_id")
        pubber_pid = self.pubber_info.get("pid")
        if self.pubber_process and self.pubber_process.poll() is None:
            pubber_alive = True
            pubber_evidence = f"tracked process {self.pubber_process.pid}"
        else:
            external = find_processes(PUBBER_PROCESS_PATTERN)
            pubber_alive = bool(external)
            if pubber_alive:
                pubber_pid = external[0]
                pubber_evidence = f"external process {external[0]}"
            else:
                pubber_evidence = "no matching process"

        # Check overall state
        if self.is_starting:
            overall = "INITIALIZING"
        elif mqtt_up and udmis_up:
            overall = "UP"
        elif mqtt_up or udmis_up or etcd_up:
            overall = "INITIALIZING"
        elif self.last_error:
            overall = "ERROR"
        else:
            overall = "DOWN"

        def _comp_status(is_up: bool, label_when_down: str = "DOWN") -> str:
            if is_up:
                return "UP"
            if self.is_starting:
                return "INITIALIZING"
            return label_when_down

        return {
            "overall": overall,
            "project_spec": self.active_project_spec,
            "site_model": self.active_site_model,
            "last_error": self.last_error,
            "components": {
                "mqtt_broker": {
                    "name": "Local Mosquitto Broker",
                    "status": _comp_status(mqtt_up),
                    "port": mqtt_port,
                    "probe": f"tcp://localhost:{mqtt_port}",
                },
                "udmis": {
                    "name": "Local UDMIS Pod",
                    "status": _comp_status(udmis_up),
                    "sentinel": "var/pod_ready.txt",
                    "sentinel_exists": udmis_sentinel,
                    "process_alive": udmis_alive,
                    "probe": "sentinel + process",
                },
                "etcd": {
                    "name": "etcd State Store",
                    "status": _comp_status(etcd_up),
                    "port": self.etcd_port,
                    "probe": f"tcp://localhost:{self.etcd_port}",
                },
                "pubber": {
                    "name": "Pubber Emulator",
                    "status": "UP" if pubber_alive else "DOWN",
                    "device_id": pubber_dev,
                    "pid": pubber_pid,
                    "probe": pubber_evidence,
                },
            },
        }

    def get_logs(self, component: str = "setup", tail: int = 100) -> Dict[str, Any]:
        """Reads recent log entries for a given component."""
        comp = (component or "setup").lower().strip()
        lines_count = max(10, min(1000, tail))

        log_file = self.setup_log_path
        if comp == "pubber":
            log_file = self.pubber_log_path
        elif comp == "udmis":
            candidate = os.path.join(self.out_dir, "udmis.log")
            if os.path.isfile(candidate):
                log_file = candidate
        elif comp == "mosquitto":
            candidate = os.path.join(self.out_dir, "mosquitto.log")
            if os.path.isfile(candidate):
                log_file = candidate

        content = ""
        if os.path.isfile(log_file):
            try:
                with open(log_file, "r", errors="replace") as f:
                    all_lines = f.readlines()
                    content = "".join(all_lines[-lines_count:])
            except Exception as e:
                content = f"Error reading log file {log_file}: {e}"
        else:
            content = f"No logs available yet for component '{comp}'."

        return {
            "component": comp,
            "log_path": os.path.relpath(log_file, self.udmi_root),
            "logs": content,
        }

    def shutdown(self) -> None:
        """Cleans up any running Pubber subprocess during gateway shutdown."""
        self._stop_pubber_internal()
