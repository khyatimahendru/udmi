"""Universal CLI Dispatcher for Mantis (Interactive / Headless / --mcp)."""

import os
import sys
from typing import List, Optional

from mantis.agent import MantisAgent
from mantis.chat import ChatConsole


def main(argv: Optional[List[str]] = None) -> int:
    """Universal entrypoint for Mantis."""
    if argv is None:
        argv = sys.argv[1:]

    # Check for --mcp flag
    if "--mcp" in argv:
        from mantis import mcp_server
        mcp_server.main()
        return 0

    # Check for --offline flag
    if "--offline" in argv:
        os.environ["MANTIS_OFFLINE"] = "true"
        argv = [a for a in argv if a != "--offline"]

    # Check for --vertex flag
    vertex_args = [a for a in argv if a.startswith("--vertex")]
    if vertex_args:
        for v in vertex_args:
            argv = [a for a in argv if a != v]
            spec = v.split("=", 1)[1] if "=" in v else "AUTO"
            if spec != "AUTO" and "/" in spec:
                p, r = spec.split("/", 1)
                if p:
                    os.environ["GOOGLE_CLOUD_PROJECT"] = p
                if r:
                    os.environ["GOOGLE_CLOUD_REGION"] = r
            elif spec != "AUTO" and spec:
                os.environ["GOOGLE_CLOUD_PROJECT"] = spec

    # Check for help
    if "-h" in argv or "--help" in argv:
        print("""Mantis: Autonomous UDMI Agent & Diagnostic Management Control Plane

Usage:
  bin/mantis                     Launch interactive diagnostic session
  bin/mantis "<instruction>"     Execute instruction or query headless
  bin/mantis <bundle.zip>        Autonomously triage support bundle
  bin/mantis --mcp               Run stdio Model Context Protocol (MCP) server
  bin/mantis --offline           Force offline deterministic mode

Provider Configuration:
  Default: Google Cloud Vertex AI (Project: bos-platform-dev, Region: global)
  To override GCP Project/Region:
    export GCP_PROJECT="my-project"
    export GCP_REGION="us-central1"
    or CLI: bin/mantis --vertex my-project/us-central1
  To use Google AI Studio:
    export GEMINI_API_KEY="AIzaSy..."
  To force offline mode:
    export MANTIS_OFFLINE=true (or pass --offline)

Examples:
  bin/mantis "Bring up the local sequencer setup for sites/udmi_site_model"
  bin/mantis "Why did pointset_publish fail for AHU-1?"
  bin/mantis "What are the required fields in pointset schema?"
  bin/mantis "Start an isolated local environment with DUT AHU-1"
  bin/mantis "Set sample_rate_sec to 10 for AHU-1 in sites/udmi_site_model"
  bin/mantis support_bundle.zip
""")
        return 0

    # Check for version
    if "--version" in argv or "-v" in argv:
        print("Mantis v2.0.0 (Unified UDMI Diagnostic Engine)")
        return 0

    # Filter any empty args
    cleaned_args = [a for a in argv if a.strip()]

    # Case 1: No arguments -> Interactive REPL
    if not cleaned_args:
        console = ChatConsole()
        console.start()
        return 0

    # Case 2: Headless Single-Shot Execution
    instruction = " ".join(cleaned_args)
    agent = MantisAgent()
    output = agent.run_headless(instruction)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
