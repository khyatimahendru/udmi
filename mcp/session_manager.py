"""Session and process manager for UDMI test infrastructure using tmux."""

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional


class SessionManager:
    """Manages isolated UDMI local test infrastructure instances inside tmux sessions."""

    def __init__(self, udmi_root: Optional[str] = None):
        if udmi_root is None:
            # Fallback to repo root relative to this file
            udmi_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.udmi_root = os.path.abspath(udmi_root)
        self.instances_dir = os.path.join(self.udmi_root, "var", "instances")
        os.makedirs(self.instances_dir, exist_ok=True)

    def sanitize_session_name(self, test_id: str) -> str:
        """Derive a valid tmux session name from a test_id string."""
        clean_id = re.sub(r"[^a-zA-Z0-9_-]", "_", test_id.strip())
        if not clean_id:
            clean_id = "default"
        if not clean_id.startswith("udmi_"):
            return f"udmi_{clean_id}"
        return clean_id

    def is_port_available(self, port: int) -> bool:
        """Check if a local TCP port is free for binding."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False

    def is_port_block_available(self, base_port: int) -> bool:
        """Check if the required block of ports is available."""
        # Check MQTT (P), etcd (P+1), influx (P+2), postgres (P+3), etcd-peer (P+1001)
        required_ports = [
            base_port,
            base_port + 1,
            base_port + 2,
            base_port + 3,
            base_port + 1001,
        ]
        return all(self.is_port_available(p) for p in required_ports)

    def derive_port_block(
        self,
        test_id: str,
        base_min: int = 20000,
        base_max: int = 55000,
        block_size: int = 10,
    ) -> int:
        """Deterministically map a test_id to an available port block."""
        hash_val = int(hashlib.sha256(test_id.encode("utf-8")).hexdigest(), 16)
        slot_count = (base_max - base_min) // block_size
        start_slot = hash_val % slot_count

        for i in range(slot_count):
            slot = (start_slot + i) % slot_count
            candidate_port = base_min + (slot * block_size)
            if self.is_port_block_available(candidate_port):
                return candidate_port

        raise RuntimeError(
            f"No available port block found in range [{base_min}, {base_max}] for test_id '{test_id}'"
        )

    def is_session_active(self, session_name: str) -> bool:
        """Check if a tmux session is currently alive."""
        res = subprocess.run(
            ["tmux", "has-session", "-t", session_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return res.returncode == 0

    def get_session_info(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored session information if available."""
        session_name = self.sanitize_session_name(test_id)
        info_path = os.path.join(self.instances_dir, session_name, "session_info.json")
        if os.path.isfile(info_path):
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if self.is_session_active(session_name):
                        data["windows"] = self.list_test_windows(test_id)
                    return data
            except Exception:
                return None
        return None

    def ensure_test_setup(
        self,
        test_id: str,
        site_model: str = "sites/udmi_site_model",
        dut_device_id: Optional[str] = None,
        dut_serial_no: Optional[str] = None,
        exclude: Optional[List[str]] = None,
        added: Optional[List[str]] = None,
        clean: bool = True,
        timeout_seconds: int = 150,
    ) -> Dict[str, Any]:
        """Start or ensure isolated local UDMI infrastructure inside a tmux session."""
        session_name = self.sanitize_session_name(test_id)
        run_dir = os.path.join(self.instances_dir, session_name)
        info_path = os.path.join(run_dir, "session_info.json")

        if site_model.startswith("//"):
            raise ValueError(
                f"'{site_model}' is a target project spec, not a site model directory. "
                f"For cloud endpoints, use run_sequencer_test(..., target_spec='{site_model}') instead."
            )

        site_model_path = os.path.abspath(os.path.join(self.udmi_root, site_model))
        if not os.path.isdir(site_model_path):
            site_model_path = os.path.abspath(site_model)

        if not os.path.isdir(site_model_path):
            raise ValueError(f"Site model directory not found: {site_model}")

        # Check if already running
        if not clean and self.is_session_active(session_name):
            existing_info = self.get_session_info(test_id)
            if existing_info:
                mqtt_port = existing_info.get("ports", {}).get("mqtt")
                if mqtt_port and self._probe_tcp("127.0.0.1", mqtt_port, timeout=1.0):
                    existing_info["status"] = "ALREADY_ACTIVE"
                    return existing_info

        # Always clean previous session and workspace if clean=True or inactive
        self.terminate_test_setup(test_id, clean_workspace=clean)

        # Allocate port
        mqtt_port = self.derive_port_block(test_id)
        etcd_port = mqtt_port + 1
        influx_port = mqtt_port + 2
        postgres_port = mqtt_port + 3

        os.makedirs(os.path.join(run_dir, "var"), exist_ok=True)
        os.makedirs(os.path.join(run_dir, "out"), exist_ok=True)

        project_spec = f"//mqtt/localhost:{mqtt_port}"
        connection_url = f"mqtt://rocket:monkey@localhost:{mqtt_port}"

        # Build filter flags
        filter_flags = []
        if exclude:
            if isinstance(exclude, str):
                exclude = [s.strip() for s in exclude.split(",") if s.strip()]
            for svc in exclude:
                filter_flags.append(f"!{svc}")
        if added:
            if isinstance(added, str):
                added = [s.strip() for s in added.split(",") if s.strip()]
            for svc in added:
                filter_flags.append(f"++{svc}")

        filter_str = (" " + " ".join(filter_flags)) if filter_flags else ""

        # Build start_local command
        main_log_file = os.path.join(run_dir, "main.log")
        start_cmd = (
            f"export UDMI_ROOT='{self.udmi_root}' && "
            f"export UDMI_RUN_DIR='{run_dir}' && "
            f"export MQTT_PORT='{mqtt_port}' && "
            f"export ETCD_PORT='{etcd_port}' && "
            f"export INFLUX_PORT='{influx_port}' && "
            f"export POSTGRES_PORT='{postgres_port}' && "
            f"export UDMI_NO_SUDO='true' && "
            f"cd '{self.udmi_root}' && "
            f"bin/start_local block '{site_model_path}' '{project_spec}'{filter_str} 2>&1 | tee '{main_log_file}'"
        )

        # Launch in background tmux session
        subprocess.run(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                session_name,
                "-n",
                "main",
                f"bash -c {json.dumps(start_cmd)}",
            ],
            check=True,
        )

        # Enable remain-on-exit so pane logs are preserved if process crashes
        subprocess.run(
            ["tmux", "set-option", "-t", session_name, "remain-on-exit", "on"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Poll readiness
        ready = self._wait_for_readiness(
            session_name=session_name,
            run_dir=run_dir,
            site_model_path=site_model_path,
            port=mqtt_port,
            timeout_seconds=timeout_seconds,
        )

        if not ready:
            logs = self.get_test_logs(test_id, window="main", lines=60)
            self.terminate_test_setup(test_id, clean_workspace=False)
            raise TimeoutError(
                f"Test setup '{test_id}' failed to become ready within {timeout_seconds}s.\n"
                f"Recent console output:\n{logs}"
            )

        # Optionally launch DUT
        if dut_device_id:
            dut_serial = dut_serial_no or f"dut-{test_id}"
            dut_cmd = (
                f"export UDMI_ROOT='{self.udmi_root}' && "
                f"export UDMI_RUN_DIR='{run_dir}' && "
                f"cd '{self.udmi_root}' && "
                f"bin/start_dut '{site_model_path}' '{project_spec}' '{dut_device_id}' '{dut_serial}'"
            )
            subprocess.run(
                [
                    "tmux",
                    "new-window",
                    "-t",
                    session_name,
                    "-n",
                    "dut",
                    f"bash -c {json.dumps(dut_cmd)}",
                ],
                check=False,
            )

        windows = self.list_test_windows(test_id)

        result_info = {
            "status": "READY",
            "test_id": test_id,
            "session_name": session_name,
            "connection_url": connection_url,
            "project_spec": project_spec,
            "windows": windows,
            "tls": {
                "ca_cert": os.path.join(site_model_path, "reflector", "ca.crt"),
                "client_cert": os.path.join(site_model_path, "reflector", "rsa_private.crt"),
                "client_key": os.path.join(site_model_path, "reflector", "rsa_private.pem"),
            },
            "credentials": {
                "username": "rocket",
                "password": "monkey",
            },
            "ports": {
                "mqtt": mqtt_port,
                "etcd": etcd_port,
                "influx": influx_port,
                "postgres": postgres_port,
            },
            "exclude": exclude or [],
            "added": added or [],
            "site_model": site_model_path,
            "run_dir": run_dir,
        }

        with open(info_path, "w", encoding="utf-8") as f:
            json.dump(result_info, f, indent=2)

        return result_info

    def terminate_test_setup(
        self, test_id: str, clean_workspace: bool = True
    ) -> Dict[str, Any]:
        """Terminate an active test setup, its child background daemons, and its tmux session."""
        session_name = self.sanitize_session_name(test_id)
        run_dir = os.path.join(self.instances_dir, session_name)

        if self.is_session_active(session_name):
            subprocess.run(
                ["tmux", "kill-session", "-t", session_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            time.sleep(0.5)

        # Forcefully terminate any orphan child processes tied to this instance workspace
        if os.path.isdir(run_dir):
            subprocess.run(
                ["pkill", "-9", "-f", run_dir],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

        if clean_workspace and os.path.isdir(run_dir):
            shutil.rmtree(run_dir, ignore_errors=True)

        return {
            "status": "TERMINATED",
            "test_id": test_id,
            "session_name": session_name,
        }

    def list_test_windows(self, test_id: str) -> List[str]:
        """List available semantic window tags for an active test session."""
        session_name = self.sanitize_session_name(test_id)
        if not self.is_session_active(session_name):
            return []

        res = subprocess.run(
            ["tmux", "list-windows", "-t", session_name, "-F", "#{window_name}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            return []

        windows = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        return windows

    def list_test_setups(self) -> List[Dict[str, Any]]:
        """List all active UDMI test sessions."""
        res = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            return []

        active_sessions = []
        for line in res.stdout.strip().splitlines():
            sname = line.strip()
            if sname.startswith("udmi_"):
                test_id = sname[5:]
                info = self.get_session_info(test_id) or {
                    "status": "ACTIVE",
                    "test_id": test_id,
                    "session_name": sname,
                }
                info["windows"] = self.list_test_windows(test_id)
                active_sessions.append(info)
        return active_sessions

    def get_test_logs(
        self, test_id: str, window: str = "main", lines: int = 100
    ) -> str:
        """Capture recent pane logs from a named semantic tmux window or fallback log file."""
        session_name = self.sanitize_session_name(test_id)
        run_dir = os.path.join(self.instances_dir, session_name)
        main_log_file = os.path.join(run_dir, "main.log")

        if not self.is_session_active(session_name):
            if os.path.isfile(main_log_file):
                try:
                    with open(main_log_file, "r", encoding="utf-8", errors="replace") as f:
                        all_lines = f.readlines()
                        return "".join(all_lines[-lines:])
                except Exception:
                    pass
            raise RuntimeError(f"Session '{session_name}' for test_id '{test_id}' is not active.")

        # Reject numerical indices to enforce semantic window tags
        if str(window).strip().isdigit():
            available = self.list_test_windows(test_id)
            raise ValueError(
                f"Window parameter must be a semantic tag (e.g. 'main', 'dut'), not a numerical index '{window}'. "
                f"Available semantic windows: {available}"
            )

        available_windows = self.list_test_windows(test_id)
        if window not in available_windows:
            raise ValueError(
                f"Semantic window '{window}' not found in session '{session_name}'. "
                f"Available semantic windows: {available_windows}"
            )

        target = f"{session_name}:{window}"
        res = subprocess.run(
            ["tmux", "capture-pane", "-t", target, "-p", "-S", f"-{lines}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout
        return f"(Could not capture logs for {target}: {res.stderr.strip()})"

    def _probe_tcp(self, host: str, port: int, timeout: float = 1.0) -> bool:
        """Attempt a simple TCP connection."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (OSError, socket.timeout):
            return False

    def _wait_for_readiness(
        self,
        session_name: str,
        run_dir: str,
        site_model_path: str,
        port: int,
        timeout_seconds: int,
    ) -> bool:
        """Wait until Mosquitto, UDMIS pod_ready, and certificates are all present and ready."""
        start_time = time.time()
        pod_ready_file = os.path.join(run_dir, "var", "pod_ready.txt")
        ca_cert_file = os.path.join(site_model_path, "reflector", "ca.crt")

        while time.time() - start_time < timeout_seconds:
            # Check if session died prematurely
            if not self.is_session_active(session_name):
                return False

            # Check Mosquitto port
            tcp_ok = self._probe_tcp("127.0.0.1", port, timeout=0.5)

            # Check pod_ready.txt
            pod_ok = os.path.isfile(pod_ready_file) or os.path.isfile(
                os.path.join(self.udmi_root, "var", "pod_ready.txt")
            )

            # Check CA certificate
            ca_ok = os.path.isfile(ca_cert_file) and os.path.getsize(ca_cert_file) > 0

            if tcp_ok and pod_ok and ca_ok:
                return True

            time.sleep(0.5)

        return False

    def validate_session_command(self, command: str) -> None:
        """Validate command against security policy and allowlisted executables."""
        if not command or not command.strip():
            raise ValueError("Command string cannot be empty.")

        clean_cmd = command.strip()

        # Reject dangerous shell injection tokens
        disallowed_patterns = [
            r"\bsudo\b",
            r"\bsu\b",
            r"\bcurl\b",
            r"\bwget\b",
            r"\bmkfifo\b",
            r"\bnc\b",
            r"\bncat\b",
            r"/dev/tcp",
            r"chmod\s+777\s+/",
            r"rm\s+-rf\s+/[^\s]*",
            r":\(\)\s*\{",
        ]
        for pat in disallowed_patterns:
            if re.search(pat, clean_cmd, re.IGNORECASE):
                raise ValueError(
                    f"Command rejected: contains disallowed security token matching '{pat}'."
                )

        # Check subcommands split by &&, ;, or |
        subcommands = re.split(r"&&|;|\|", clean_cmd)
        allowed_prefixes = (
            "bin/",
            "java",
            "python",
            "python3",
            "venv/bin/python",
            "venv/bin/python3",
            "pytest",
            "export",
            "cd",
            "echo",
        )

        for sub in subcommands:
            s = sub.strip()
            if not s:
                continue
            # Remove leading environment variable assignments e.g. "FOO=BAR bin/sequencer"
            s_no_env = re.sub(r"^[A-Za-z0-9_]+=[^\s]+\s+", "", s).strip()
            if not any(s_no_env.startswith(prefix) for prefix in allowed_prefixes):
                raise ValueError(
                    f"Command segment '{s}' rejected: executable must start with an approved prefix: {allowed_prefixes}"
                )

    def start_session_process(
        self,
        test_id: str,
        window: str,
        command: str,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Launch a command or test process inside a named semantic window of an active session."""
        self.validate_session_command(command)

        session_name = self.sanitize_session_name(test_id)
        if not self.is_session_active(session_name):
            raise RuntimeError(f"Session '{session_name}' for test_id '{test_id}' is not active.")

        if str(window).strip().isdigit():
            raise ValueError(
                f"Window parameter must be a semantic tag (e.g. 'sequencer', 'dut'), not a numerical index '{window}'."
            )

        run_dir = os.path.join(self.instances_dir, session_name)
        info = self.get_session_info(test_id) or {}
        ports = info.get("ports", {})
        mqtt_port = ports.get("mqtt", self.derive_port_block(test_id))

        env_exports = [
            f"export UDMI_ROOT='{self.udmi_root}'",
            f"export UDMI_RUN_DIR='{run_dir}'",
            f"export MQTT_PORT='{mqtt_port}'",
            f"export UDMI_NO_SUDO='true'",
        ]
        if env:
            for k, v in env.items():
                env_exports.append(f"export {k}='{v}'")

        full_cmd = f"{' && '.join(env_exports)} && cd '{self.udmi_root}' && {command}"

        existing_windows = self.list_test_windows(test_id)
        if window in existing_windows:
            subprocess.run(
                ["tmux", "send-keys", "-t", f"{session_name}:{window}", full_cmd, "C-m"],
                check=True,
            )
        else:
            subprocess.run(
                [
                    "tmux",
                    "new-window",
                    "-t",
                    session_name,
                    "-n",
                    window,
                    f"bash -c {json.dumps(full_cmd)}",
                ],
                check=True,
            )

        return {
            "status": "STARTED",
            "test_id": test_id,
            "session_name": session_name,
            "window": window,
            "command": command,
        }

    def run_sequencer_test(
        self,
        test_name: str,
        device_id: str = "AHU-1",
        target_spec: Optional[str] = None,
        site_model: str = "sites/udmi_site_model",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Launch a sequencer test against a local or cloud endpoint."""
        # Handle accidental swap where user or model passed //... as site_model
        if site_model.startswith("//") and not target_spec:
            target_spec = site_model
            site_model = "sites/udmi_site_model"

        site_model_path = os.path.abspath(os.path.join(self.udmi_root, site_model))
        if not os.path.isdir(site_model_path):
            site_model_path = os.path.abspath(site_model)
        if not os.path.isdir(site_model_path):
            raise ValueError(f"Site model directory not found: {site_model}")

        # Determine target project spec
        is_cloud = False
        if target_spec and (
            any(target_spec.startswith(p) for p in ("//gbos", "//gcp", "//gref", "//iotcore", "//reflect"))
            or (target_spec.startswith("//") and not re.match(r"^//mqtt/(?:localhost|127\.0\.0\.1)", target_spec, re.IGNORECASE))
        ):
            is_cloud = True
            resolved_target = target_spec
            sess_name = self.sanitize_session_name(session_id or f"cloud_{device_id}_{test_name}")
        elif target_spec and target_spec.startswith("//"):
            resolved_target = target_spec
            sess_name = self.sanitize_session_name(session_id or f"test_{device_id}_{test_name}")
        else:
            active_info = self.get_session_info(session_id) if session_id else None
            if active_info and "project_spec" in active_info:
                resolved_target = active_info["project_spec"]
                sess_name = self.sanitize_session_name(session_id)
            else:
                active_setups = self.list_test_setups()
                if active_setups:
                    first_sess = active_setups[0].get("test_id", "")
                    first_info = self.get_session_info(first_sess) or {}
                    resolved_target = first_info.get("project_spec")
                    sess_name = self.sanitize_session_name(first_sess)
                else:
                    resolved_target = None
                    sess_name = self.sanitize_session_name(session_id or f"test_{device_id}_{test_name}")

        # If not cloud and no active session/target, ensure local test setup
        if not is_cloud and not resolved_target:
            setup_info = self.ensure_test_setup(test_id=sess_name, site_model=site_model, dut_device_id=device_id)
            resolved_target = setup_info["project_spec"]

        # Ensure session exists (for cloud or background execution)
        run_dir = os.path.join(self.instances_dir, sess_name)
        os.makedirs(os.path.join(run_dir, "out"), exist_ok=True)
        os.makedirs(os.path.join(run_dir, "var"), exist_ok=True)

        if not self.is_session_active(sess_name):
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", sess_name, "-n", "sequencer"],
                check=True,
            )
            subprocess.run(
                ["tmux", "set-option", "-t", sess_name, "remain-on-exit", "on"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        cmd = f"bin/sequencer '{site_model_path}' '{resolved_target}' '{device_id}' '{test_name}'"
        res = self.start_session_process(test_id=sess_name, window="sequencer", command=cmd)

        return {
            "status": "LAUNCHED",
            "test_name": test_name,
            "device_id": device_id,
            "site_model": site_model,
            "target_spec": resolved_target,
            "session_id": sess_name,
            "window": "sequencer",
            "command": cmd,
            "is_cloud": is_cloud,
            "message": (
                f"Launched sequencer test '{test_name}' for device '{device_id}' against '{resolved_target}' "
                f"in session '{sess_name}' (window: 'sequencer')."
            ),
        }

    def query_database(
        self,
        test_id: str,
        database_type: str,
        query: str,
    ) -> Dict[str, Any]:
        """Execute a read-only query against InfluxDB or PostgreSQL of an active test session."""
        db_type = database_type.lower().strip()
        if db_type not in ("influx", "postgres"):
            raise ValueError(f"Unsupported database_type: '{database_type}'. Must be 'influx' or 'postgres'.")

        # Safety check: enforce read-only query
        forbidden_keywords = [
            "insert", "update", "delete", "drop", "alter", "create",
            "truncate", "grant", "revoke", "copy", "replace", "vacuum"
        ]
        query_words = set(re.findall(r"\b[a-zA-Z]+\b", query.lower()))
        for kw in forbidden_keywords:
            if kw in query_words:
                raise ValueError(f"Mutating query rejected. Only read-only queries are permitted (found '{kw}').")

        info = self.get_session_info(test_id) or {}
        ports = info.get("ports", {})

        if db_type == "influx":
            influx_port = ports.get("influx")
            if not influx_port:
                influx_port = self.derive_port_block(test_id) + 2

            import urllib.parse
            import urllib.request
            params = urllib.parse.urlencode({"db": "udmi", "q": query})
            url = f"http://127.0.0.1:{influx_port}/query?{params}"
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return {
                        "status": "SUCCESS",
                        "test_id": test_id,
                        "database_type": "influx",
                        "query": query,
                        "results": data.get("results", []),
                    }
            except Exception as e:
                return {
                    "status": "ERROR",
                    "test_id": test_id,
                    "database_type": "influx",
                    "query": query,
                    "error": str(e),
                }

        elif db_type == "postgres":
            pg_port = ports.get("postgres")
            if not pg_port:
                pg_port = self.derive_port_block(test_id) + 3

            try:
                import psycopg2
                conn = psycopg2.connect(
                    host="127.0.0.1",
                    port=pg_port,
                    dbname="udmi",
                    user="postgres",
                    connect_timeout=3,
                )
                try:
                    with conn.cursor() as cur:
                        cur.execute(query)
                        if cur.description:
                            columns = [desc[0] for desc in cur.description]
                            rows = cur.fetchall()
                            rows_dict = [dict(zip(columns, row)) for row in rows]
                            return {
                                "status": "SUCCESS",
                                "test_id": test_id,
                                "database_type": "postgres",
                                "query": query,
                                "columns": columns,
                                "results": rows_dict,
                            }
                        return {
                            "status": "SUCCESS",
                            "test_id": test_id,
                            "database_type": "postgres",
                            "query": query,
                            "results": [],
                        }
                finally:
                    conn.close()
            except Exception as e:
                return {
                    "status": "ERROR",
                    "test_id": test_id,
                    "database_type": "postgres",
                    "query": query,
                    "error": str(e),
                }

    def publish_mqtt_message(
        self,
        test_id: str,
        topic: str,
        payload: str,
    ) -> Dict[str, Any]:
        """Publish a message to Mosquitto MQTT broker of an active test session."""
        info = self.get_session_info(test_id) or {}
        ports = info.get("ports", {})
        mqtt_port = ports.get("mqtt")
        if not mqtt_port:
            mqtt_port = self.derive_port_block(test_id)

        try:
            import paho.mqtt.publish as publish
            publish.single(
                topic=topic,
                payload=payload,
                hostname="127.0.0.1",
                port=mqtt_port,
                auth={"username": "rocket", "password": "monkey"},
            )
            return {
                "status": "PUBLISHED",
                "test_id": test_id,
                "topic": topic,
                "payload": payload,
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "test_id": test_id,
                "topic": topic,
                "error": str(e),
            }

