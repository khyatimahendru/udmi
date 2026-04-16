import click
from .ingestion import ingest_logs
from .weaver import synchronize_logs
from .ai import analyze_failure
from .reporting import report_results
from .db import record_test_run, get_test_history

@click.group()
def cli():
    """UDMI Sentinel: AI-powered test failure analysis."""
    pass

@cli.command()
@click.option('--local-logs', type=click.Path(exists=True, file_okay=False, dir_okay=True), help='Path to local log directory.')
@click.option('--archive', type=click.Path(exists=True, file_okay=True, dir_okay=False), help='Path to UDMI support bundle archive (.tgz).')
@click.option('--ci', is_flag=True, help='Run in CI mode (fetches logs from CI environment variables).')
@click.option('--api-key', envvar='GEMINI_API_KEY', required=True, help='Gemini API key for analysis.')
def analyze(local_logs, archive, ci, api_key):
    """Analyze test failures and report root cause."""
    if not local_logs and not archive and not ci:
        click.echo("Error: Must provide either --local-logs, --archive, or --ci")
        return

    click.echo("Starting UDMI Sentinel...")

    # Step 1: Ingestion
    click.echo("Ingesting logs...")
    # Prefer archive over local_logs over CI
    raw_logs = ingest_logs(
        local_dir=local_logs if local_logs else None,
        archive_path=archive if archive else None,
        is_ci=ci if (not local_logs and not archive) else False
    )

    # Step 2: Historical Lookup
    # A generic test suite run for now
    test_suite_name = "udmi_test_suite"
    history = get_test_history(test_suite_name)

    # Record the current run as a failure (since Sentinel is only invoked on failure)
    record_test_run(test_suite_name, "fail")

    # Step 3 & 4: Normalization and Correlation (The Weaver)
    click.echo("Synchronizing timelines...")
    timeline = synchronize_logs(raw_logs)

    # Step 5 & 6: AI Analysis
    click.echo("Running AI analysis...")
    analysis = analyze_failure(timeline, history, api_key)

    # Step 7: Reporting
    click.echo("Generating report...")
    report_results(analysis, is_ci=ci)

if __name__ == '__main__':
    cli()
