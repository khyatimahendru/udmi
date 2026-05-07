import click
import os
import json

def report_results(analysis, is_ci=False):
    """
    Outputs the analysis to the appropriate channel.
    """

    report_text = f"""
========================================
         UDMI Sentinel Analysis
========================================
Classification   : {analysis.get('classification', 'unknown').upper()}
Confidence       : {analysis.get('confidence', 0.0) * 100:.1f}%
Component        : {analysis.get('component_at_fault', 'unknown')}
----------------------------------------
Root Cause:
{analysis.get('root_cause', 'No analysis available.')}
========================================
"""

    if not is_ci:
        # Local Developer Mode: Print nicely to terminal
        if analysis.get('classification') == 'flake':
            click.secho(report_text, fg='yellow')
        elif analysis.get('classification') == 'hard_failure':
            click.secho(report_text, fg='red')
        else:
            click.secho(report_text, fg='white')
    else:
        # CI Mode: Write to a file that can be picked up by PR comment actions
        # and print to stdout for CI logs
        print(report_text)

        output_file = os.environ.get('SENTINEL_OUTPUT_FILE', 'sentinel_report.md')
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_text)
            print(f"Report written to {output_file}")
        except Exception as e:
            print(f"Warning: Failed to write report file: {e}")

        # In a real CI setup, we might also use Github Actions step summaries:
        # if "GITHUB_STEP_SUMMARY" in os.environ:
        #     with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
        #         f.write(report_text)
