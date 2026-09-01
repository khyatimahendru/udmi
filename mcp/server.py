#!/usr/bin/env python3
"""UDMI Test Infrastructure MCP Server & CLI Tool.

Supports:
1. Standard MCP JSON-RPC 2.0 protocol over stdio for AI agent tool calling.
2. Direct CLI invocation (e.g. `bin/test_setup ensure <test_id>`) for CI and manual workflows.
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

from mcp.session_manager import SessionManager
from mantis.tools.artifacts import extract_timeline
from mantis.tools.diagnostics import diagnose_test_failure
from mantis.tools.differential import compare_test_runs
from mantis.tools.patcher import patch_site_model
from mantis.tools.schemas import inspect_udmi_schema
from mantis.tools.site_models import inspect_site_model


from mantis.tools.registry import get_mcp_tools

MCP_TOOLS = get_mcp_tools()


from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse


class MCPHttpHandler(BaseHTTPRequestHandler):
    """HTTP & SSE Request Handler for remote MCP transport."""

    server_instance: Any = None

    def log_message(self, format, *args):
        """Suppress noisy default request logging to stderr."""
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(
                json.dumps({
                    "status": "OK",
                    "server": "udmi-test-infra",
                    "version": "1.0.0",
                    "tools_count": len(MCP_TOOLS),
                }).encode("utf-8")
            )
        elif parsed.path == "/sse":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            endpoint_msg = "event: endpoint\ndata: /message\n\n"
            self.wfile.write(endpoint_msg.encode("utf-8"))
            self.wfile.flush()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/message", "/rpc", "/"):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                req = json.loads(body)
                resp = self.server_instance.handle_request(req)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                if resp is not None:
                    self.wfile.write(json.dumps(resp).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                err = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(e)},
                }
                self.wfile.write(json.dumps(err).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


class MCPServer:
    """Handles JSON-RPC 2.0 MCP messages over stdio or HTTP/SSE with both sync and async support."""

    def __init__(self, session_mgr: SessionManager):
        self.session_mgr = session_mgr

    def run_http(self, host: str = "127.0.0.1", port: int = 8080) -> HTTPServer:
        """Create and bind HTTP/SSE server instance."""
        MCPHttpHandler.server_instance = self
        return HTTPServer((host, port), MCPHttpHandler)

    def run(self) -> None:
        """Main stdio loop for MCP protocol."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(e)},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()

    async def run_async(self) -> None:
        """Asynchronous non-blocking stdio loop for MCP protocol."""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            line_bytes = await reader.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8").strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = await self.handle_request_async(request)
                if response is not None:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(e)},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()

    async def handle_request_async(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Asynchronously processes an MCP request, delegating blocking tools to a background thread."""
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "udmi-test-infra",
                        "version": "1.0.0",
                    },
                },
            }

        if method == "notifications/initialized":
            return None

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}}

        if method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                loop = asyncio.get_running_loop()
                result_data = await loop.run_in_executor(
                    None, self.execute_tool, tool_name, tool_args
                )
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result_data, indent=2) if not isinstance(result_data, str) else result_data,
                            }
                        ],
                        "isError": False,
                    },
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {e}"}],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "udmi-test-infra",
                        "version": "1.0.0",
                    },
                },
            }

        if method == "notifications/initialized":
            return None

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}}

        if method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                result_data = self.execute_tool(tool_name, tool_args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result_data, indent=2) if not isinstance(result_data, str) else result_data,
                            }
                        ],
                        "isError": False,
                    },
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {e}"}],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        from mantis.tools.registry import execute_tool as reg_execute
        return reg_execute(name=name, args=args, session_mgr=self.session_mgr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="UDMI Test Infrastructure Control (MCP Server & CLI)"
    )
    subparsers = parser.add_subparsers(dest="command")

    # ensure subcommand
    ensure_parser = subparsers.add_parser(
        "ensure", help="Start or ensure isolated local UDMI test infrastructure"
    )
    ensure_parser.add_argument("test_id", help="Unique identifier for the test run")
    ensure_parser.add_argument(
        "site_model",
        nargs="?",
        default="sites/udmi_site_model",
        help="Path to site model (default: sites/udmi_site_model)",
    )
    ensure_parser.add_argument(
        "--dut", dest="dut_device_id", help="Device ID to launch as emulated DUT"
    )
    ensure_parser.add_argument(
        "--serial", dest="dut_serial_no", help="Serial number for emulated DUT"
    )
    ensure_parser.add_argument(
        "--exclude",
        "-x",
        nargs="*",
        dest="exclude",
        help="List of canonical services to exclude (e.g. -x udmis influxdb)",
    )
    ensure_parser.add_argument(
        "--added",
        "-a",
        nargs="*",
        dest="added",
        help="List of optional services to add (e.g. -a validator spotter)",
    )
    ensure_parser.add_argument(
        "--no-clean",
        dest="clean",
        action="store_false",
        default=True,
        help="Do not clean existing session state",
    )
    ensure_parser.add_argument(
        "--timeout",
        dest="timeout_seconds",
        type=int,
        default=150,
        help="Readiness timeout in seconds (default: 150)",
    )
    ensure_parser.add_argument(
        "--json", action="store_true", help="Output full JSON response"
    )

    # terminate subcommand
    term_parser = subparsers.add_parser(
        "terminate", help="Terminate a running test infrastructure setup"
    )
    term_parser.add_argument("test_id", help="Identifier of the test session")
    term_parser.add_argument(
        "--no-clean",
        dest="clean_workspace",
        action="store_false",
        default=True,
        help="Do not delete per-instance workspace directory",
    )
    term_parser.add_argument(
        "--json", action="store_true", help="Output full JSON response"
    )

    # list subcommand
    list_parser = subparsers.add_parser("list", help="List all active test setups")
    list_parser.add_argument(
        "--json", action="store_true", help="Output full JSON response"
    )

    # windows subcommand
    windows_parser = subparsers.add_parser(
        "windows", help="List available semantic windows for an active test session"
    )
    windows_parser.add_argument("test_id", help="Identifier of the test session")
    windows_parser.add_argument(
        "--json", action="store_true", help="Output full JSON response"
    )

    # status subcommand
    status_parser = subparsers.add_parser(
        "status", help="Get status of a specific test setup"
    )
    status_parser.add_argument("test_id", help="Identifier of the test session")
    status_parser.add_argument(
        "--json", action="store_true", help="Output full JSON response"
    )

    # logs subcommand
    logs_parser = subparsers.add_parser(
        "logs", help="View logs from a test setup tmux window"
    )
    logs_parser.add_argument("test_id", help="Identifier of the test session")
    logs_parser.add_argument(
        "window",
        nargs="?",
        default="main",
        help="Semantic window tag (default: main). Numerical indices are not permitted.",
    )
    logs_parser.add_argument(
        "-n", "--lines", type=int, default=100, help="Number of lines to capture"
    )

    # mcp subcommand
    subparsers.add_parser("mcp", help="Run in stdio MCP server mode")

    # serve subcommand
    serve_parser = subparsers.add_parser("serve", help="Run MCP server over HTTP/SSE")
    serve_parser.add_argument(
        "--port", "-p", type=int, default=8080, help="Port to listen on (default: 8080)"
    )
    serve_parser.add_argument(
        "--host", "-H", type=str, default="127.0.0.1", help="Host to bind (default: 127.0.0.1)"
    )

    args = parser.parse_args()

    session_mgr = SessionManager()

    if args.command == "ensure":
        exclude_list = []
        if args.exclude:
            for item in args.exclude:
                exclude_list.extend([s.strip() for s in item.split(",") if s.strip()])
        added_list = []
        if args.added:
            for item in args.added:
                added_list.extend([s.strip() for s in item.split(",") if s.strip()])

        res = session_mgr.ensure_test_setup(
            test_id=args.test_id,
            site_model=args.site_model,
            dut_device_id=args.dut_device_id,
            dut_serial_no=args.dut_serial_no,
            exclude=exclude_list or None,
            added=added_list or None,
            clean=args.clean,
            timeout_seconds=args.timeout_seconds,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(res["connection_url"])

    elif args.command == "terminate":
        res = session_mgr.terminate_test_setup(
            test_id=args.test_id, clean_workspace=args.clean_workspace
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Terminated {res['session_name']}")

    elif args.command == "list":
        res = session_mgr.list_test_setups()
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            if not res:
                print("No active UDMI test sessions found.")
            else:
                for item in res:
                    print(
                        f"{item.get('test_id', 'unknown')}: "
                        f"url={item.get('connection_url', 'N/A')} "
                        f"session={item.get('session_name', 'N/A')} "
                        f"windows={item.get('windows', [])}"
                    )

    elif args.command == "windows":
        windows = session_mgr.list_test_windows(args.test_id)
        if args.json:
            print(json.dumps(windows, indent=2))
        else:
            if not windows:
                print(f"No active windows found for {args.test_id}")
            else:
                print(f"Available windows for {args.test_id}: {', '.join(windows)}")

    elif args.command == "status":
        res = session_mgr.get_session_info(args.test_id)
        if res is None:
            if session_mgr.is_session_active(
                session_mgr.sanitize_session_name(args.test_id)
            ):
                res = {
                    "status": "ACTIVE_UNTRACKED",
                    "test_id": args.test_id,
                    "windows": session_mgr.list_test_windows(args.test_id),
                }
            else:
                res = {"status": "NOT_FOUND", "test_id": args.test_id}
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"Status: {res.get('status')}")
            if "connection_url" in res:
                print(f"Connection URL: {res['connection_url']}")
            if "windows" in res:
                print(f"Windows: {', '.join(res['windows'])}")

    elif args.command == "logs":
        logs = session_mgr.get_test_logs(
            test_id=args.test_id, window=args.window, lines=args.lines
        )
        print(logs)

    elif args.command == "serve":
        server = MCPServer(session_mgr)
        httpd = server.run_http(host=args.host, port=args.port)
        print(f"UDMI MCP HTTP/SSE Server running on http://{args.host}:{args.port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.server_close()

    else:
        # Default to MCP stdio mode if 'mcp' or no arguments
        server = MCPServer(session_mgr)
        server.run()


if __name__ == "__main__":
    main()
