"""Command-Line Interface (CLI) for Threat Intelligence Agent.

Built with Typer and Rich, supporting autonomous multi-agent analysis,
RAG knowledge management, persistent caching, and hermetic offline execution.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from ti_agent.core.config import Settings, get_settings
from ti_agent.core.exceptions import IndicatorValidationError
from ti_agent.core.logging import get_logger
from ti_agent.graph.workflow import analyze_threat
from ti_agent.models.indicator import ParsedIndicator
from ti_agent.models.report import ThreatReport
from ti_agent.rag.evaluation import evaluate_rag_retriever
from ti_agent.rag.ingestion import ingest_knowledge_base
from ti_agent.rag.retriever import KnowledgeRetriever

logger = get_logger("ti_agent.cli")
console = Console()
err_console = Console(stderr=True)

app = typer.Typer(
    name="ti-agent",
    help="Autonomous Multi-Agent Threat Intelligence & CVE Analysis System",
    no_args_is_help=True,
    add_completion=False,
)
rag_app = typer.Typer(
    name="rag",
    help="Manage local RAG knowledge base, vector index, and evaluation benchmark.",
    no_args_is_help=True,
)
cache_app = typer.Typer(
    name="cache",
    help="Manage persistent diskcache for external telemetry and queries.",
    no_args_is_help=True,
)

app.add_typer(rag_app, name="rag")
app.add_typer(cache_app, name="cache")

__version__ = "0.1.0"


def clear_local_cache(cache_dir: Path) -> int:
    """Clear local disk cache directory and recreate empty structure."""
    if not cache_dir.exists():
        return 0
    count = sum(1 for _ in cache_dir.rglob("*"))
    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return count


def _get_severity_style(severity: str) -> str:
    """Map severity string to rich color style."""
    match severity.upper():
        case "CRITICAL":
            return "bold red"
        case "HIGH":
            return "bold magenta"
        case "MEDIUM":
            return "bold yellow"
        case "LOW":
            return "bold green"
        case _:
            return "bold blue"


def render_rich_report_dashboard(report: ThreatReport, lang: str | None = None) -> None:
    """Render structured visual threat intelligence dashboard using Rich."""
    from ti_agent.core.i18n import resolve_language, t

    resolved_lang = resolve_language(lang or getattr(report, "language", None))
    sev_style = _get_severity_style(report.severity_level)
    none_str = t("none_observed", lang=resolved_lang)
    cves_str = ", ".join(report.correlated_cves) if report.correlated_cves else none_str

    # Executive Overview Panel
    overview_text = (
        f"[bold]{t('target', lang=resolved_lang)}:[/] [cyan]{report.target}[/]  |  "
        f"[bold]{t('type', lang=resolved_lang)}:[/] {report.target_type.value.upper()}  |  "
        f"[bold]{t('risk_score', lang=resolved_lang)}:[/] [{sev_style}]{report.risk_score:.1f} / 10.0 ({report.severity_level})[/]  |  "
        f"[bold]{t('correlated_cves', lang=resolved_lang)}:[/] {cves_str}\n\n"
        f"[bold]{t('executive_summary', lang=resolved_lang)}:[/] {report.executive_summary}\n\n"
        f"[bold]{t('risk_rationale', lang=resolved_lang)}:[/] {report.risk_rationale}"
    )

    console.print(
        Panel(
            overview_text,
            title=f"[bold white on blue] {t('dashboard_title', lang=resolved_lang)} [/]",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )

    # Technical Evidence Table
    if report.technical_evidence:
        web_insp = report.technical_evidence.get("Web Security Inspection")
        if isinstance(web_insp, dict):
            web_table = Table(
                title=t("web_audit_table_title", lang=resolved_lang),
                box=box.SIMPLE_HEAVY,
                header_style="bold cyan",
            )
            web_table.add_column(
                t("web_control_column", lang=resolved_lang), style="bold white", width=26
            )
            web_table.add_column(t("web_status_column", lang=resolved_lang), style="dim")

            for k, v in web_insp.items():
                if isinstance(v, list):
                    val_str = ", ".join(str(item) for item in v) if v else "None (PASS)"
                else:
                    val_str = str(v)
                web_table.add_row(k, val_str)

            console.print(web_table)

        other_evidence = {
            k: v for k, v in report.technical_evidence.items() if k != "Web Security Inspection"
        }
        if other_evidence:
            telemetry_table = Table(
                title=t("telemetry_table_title", lang=resolved_lang),
                box=box.SIMPLE_HEAVY,
                header_style="bold cyan",
            )
            telemetry_table.add_column(
                t("category_source_column", lang=resolved_lang), style="bold white", width=22
            )
            telemetry_table.add_column(t("observation_column", lang=resolved_lang), style="dim")

            for source_key, evidence_val in other_evidence.items():
                telemetry_table.add_row(str(source_key), str(evidence_val))

            console.print(telemetry_table)

    # MITRE ATT&CK Matrix Table
    if report.mitre_techniques:
        mitre_table = Table(
            title=t("mitre_table_title", lang=resolved_lang),
            box=box.SIMPLE_HEAVY,
            header_style="bold magenta",
        )
        mitre_table.add_column(
            t("tech_id_column", lang=resolved_lang), style="bold yellow", width=14
        )
        mitre_table.add_column(
            t("tech_name_column", lang=resolved_lang), style="bold white", width=30
        )
        mitre_table.add_column(t("tactic_column", lang=resolved_lang), style="cyan", width=20)
        mitre_table.add_column(t("behavior_notes_column", lang=resolved_lang), style="dim")

        for tech in report.mitre_techniques:
            mitre_table.add_row(
                tech.technique_id,
                tech.name,
                tech.tactic,
                tech.relevance_explanation
                or (
                    "Mapeado mediante heurísticas"
                    if resolved_lang == "es"
                    else "Mapped via threat intel heuristics"
                ),
            )
        console.print(mitre_table)

    # Mitigations Table
    if report.mitigations:
        mit_table = Table(
            title=t("mitigations_table_title", lang=resolved_lang),
            box=box.SIMPLE_HEAVY,
            header_style="bold green",
        )
        mit_table.add_column(t("priority_column", lang=resolved_lang), width=12)
        mit_table.add_column(t("category_column", lang=resolved_lang), style="cyan", width=22)
        mit_table.add_column(
            t("action_title_column", lang=resolved_lang), style="bold white", width=30
        )
        mit_table.add_column(t("remediation_column", lang=resolved_lang), style="dim")

        for mit in report.mitigations:
            p_style = (
                "bold red"
                if mit.priority == "CRITICAL"
                else "bold magenta"
                if mit.priority == "HIGH"
                else "bold yellow"
                if mit.priority == "MEDIUM"
                else "bold green"
            )
            mit_table.add_row(
                f"[{p_style}]{mit.priority}[/]",
                mit.category,
                mit.title,
                mit.description,
            )
        console.print(mit_table)


@app.command(name="analyze")
def analyze_command(
    target: Annotated[
        str,
        typer.Argument(
            help="Indicator of Compromise (IPv4, IPv6, Domain, File Hash) or CVE identifier (e.g. CVE-2021-44228).",
        ),
    ],
    offline: Annotated[
        bool,
        typer.Option(
            "--offline",
            "-O",
            help="Execute in 100% offline mode with recorded fixtures and deterministic models.",
        ),
    ] = False,
    format_type: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: 'markdown', 'json', or 'both'.",
        ),
    ] = "markdown",
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="File path to save the generated report (e.g., report.md or report.json).",
        ),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option(
            "--provider",
            "-p",
            help="Override LLM provider: 'ollama', 'openai', or 'anthropic'.",
        ),
    ] = None,
    top_k: Annotated[
        int,
        typer.Option(
            "--top-k",
            "-k",
            help="Number of RAG knowledge chunks to retrieve for contextual analysis.",
        ),
    ] = 3,
    clear_cache: Annotated[
        bool,
        typer.Option(
            "--clear-cache",
            help="Purge local cache before running analysis.",
        ),
    ] = False,
    language: Annotated[
        str,
        typer.Option(
            "--lang",
            "-l",
            help="Report language: 'auto' (detect from OS display language), 'es' (Spanish), or 'en' (English).",
        ),
    ] = "auto",
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Quiet mode: suppress progress spinners and dashboard; output raw report only.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable debug logging.",
        ),
    ] = False,
) -> None:
    """Analyze a threat indicator or CVE using the autonomous multi-agent pipeline."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Early validation of indicator format to fail fast
    try:
        ParsedIndicator.parse(target)
    except IndicatorValidationError as exc:
        err_console.print(f"[bold red]Indicator Validation Error:[/] {exc}")
        raise typer.Exit(code=1) from exc

    cfg = get_settings()

    # Determine offline setting (flag or config)
    is_offline = offline or cfg.offline_mode

    # Resolve report language
    from ti_agent.core.i18n import resolve_language

    resolved_lang = resolve_language(language, settings=cfg)

    # Handle cache clear option
    if clear_cache:
        cleared_count = clear_local_cache(cfg.cache_dir)
        if not quiet:
            console.print(f"[dim]Cleared {cleared_count} items from cache ({cfg.cache_dir}).[/]")

    # Build settings overrides
    settings_kwargs: dict[str, object] = {
        "offline_mode": is_offline,
        "rag_top_k": top_k,
        "report_language": resolved_lang,
    }
    if provider:
        settings_kwargs["llm_provider"] = provider

    run_settings = Settings(**{**cfg.model_dump(), **settings_kwargs})

    # Execute multi-agent analysis with interactive feedback
    try:
        if quiet:
            report = analyze_threat(target, settings=run_settings)
        else:
            with console.status(
                f"[bold cyan]Orchestrating multi-agent analysis for [white]{target}[/] (lang={resolved_lang}, offline={is_offline})...[/]",
                spinner="dots",
            ):
                report = analyze_threat(target, settings=run_settings)

    except IndicatorValidationError as exc:
        err_console.print(f"[bold red]Indicator Validation Error:[/] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        err_console.print(f"[bold red]Analysis Failed:[/] {exc}")
        if verbose:
            err_console.print_exception()
        raise typer.Exit(code=1) from exc

    # Render dashboard if not in quiet mode
    if not quiet:
        render_rich_report_dashboard(report, lang=resolved_lang)

    # Output formatting
    fmt = format_type.lower()
    markdown_content = report.to_markdown(lang=resolved_lang)
    json_content = report.model_dump_json(indent=2)

    # Save to file if requested
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "json":
            output.write_text(json_content, encoding="utf-8")
            if not quiet:
                console.print(f"[bold green]✓ Report exported as JSON to:[/] {output}")
        elif fmt == "both":
            md_path = output.with_suffix(".md")
            json_path = output.with_suffix(".json")
            md_path.write_text(markdown_content, encoding="utf-8")
            json_path.write_text(json_content, encoding="utf-8")
            if not quiet:
                console.print(f"[bold green]✓ Reports exported to:[/] {md_path} and {json_path}")
        else:
            # Default to markdown
            output.write_text(markdown_content, encoding="utf-8")
            if not quiet:
                console.print(f"[bold green]✓ Report exported as Markdown to:[/] {output}")

    # Standard stdout output
    if quiet:
        if fmt == "json":
            print(json_content)
        else:
            print(markdown_content)
    elif not output:
        if fmt == "json":
            console.print_json(json_content)
        elif fmt == "both":
            console.print(Markdown(markdown_content))
            console.print_json(json_content)
        else:
            console.print(Markdown(markdown_content))


@app.command(name="audit-web")
def audit_web_command(
    target: Annotated[
        str,
        typer.Argument(
            help="Target URL to audit (e.g. http://localhost:8080/dashboard or https://example.com).",
        ),
    ],
    offline: Annotated[
        bool,
        typer.Option(
            "--offline",
            "-O",
            help="Execute in 100% offline mode with recorded fixtures and deterministic models.",
        ),
    ] = False,
    format_type: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: 'markdown', 'json', or 'both'.",
        ),
    ] = "markdown",
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="File path to save the generated report (e.g., report.md or report.json).",
        ),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option(
            "--provider",
            "-p",
            help="Override LLM provider: 'ollama', 'openai', or 'anthropic'.",
        ),
    ] = None,
    top_k: Annotated[
        int,
        typer.Option(
            "--top-k",
            "-k",
            help="Number of RAG knowledge chunks to retrieve for contextual analysis.",
        ),
    ] = 3,
    clear_cache: Annotated[
        bool,
        typer.Option(
            "--clear-cache",
            help="Purge local cache before running analysis.",
        ),
    ] = False,
    language: Annotated[
        str,
        typer.Option(
            "--lang",
            "-l",
            help="Report language: 'auto' (detect from OS display language), 'es' (Spanish), or 'en' (English).",
        ),
    ] = "auto",
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Quiet mode: suppress progress spinners and dashboard; output raw report only.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable debug logging.",
        ),
    ] = False,
) -> None:
    """Audit a web application (HTTP headers, cookie flags, tech disclosure, CORS) using the multi-agent pipeline."""
    # Ensure scheme is present if user just provided host:port/path
    url_target = target
    if not url_target.startswith(("http://", "https://")):
        url_target = f"http://{url_target}"

    analyze_command(
        target=url_target,
        offline=offline,
        format_type=format_type,
        output=output,
        provider=provider,
        top_k=top_k,
        clear_cache=clear_cache,
        language=language,
        quiet=quiet,
        verbose=verbose,
    )


@rag_app.command(name="ingest")
def rag_ingest_command(
    docs_dir: Annotated[
        Path,
        typer.Option(
            "--docs-dir",
            "-d",
            help="Directory containing markdown threat intelligence knowledge documents.",
        ),
    ] = Path("knowledge_base"),
    persist_dir: Annotated[
        Path | None,
        typer.Option(
            "--persist-dir",
            "-p",
            help="Target directory for ChromaDB vectorstore persistence.",
        ),
    ] = None,
    reset: Annotated[
        bool,
        typer.Option(
            "--reset/--no-reset",
            help="Clear existing vector store before re-indexing.",
        ),
    ] = True,
) -> None:
    """Ingest markdown knowledge base documents into ChromaDB vectorstore."""
    cfg = get_settings()
    target_dir = persist_dir or cfg.chroma_persist_dir

    if reset and target_dir.exists():
        with console.status(f"[yellow]Cleaning existing vectorstore at {target_dir}...[/]"):
            shutil.rmtree(target_dir, ignore_errors=True)

    with console.status(
        f"[bold cyan]Ingesting documents from [white]{docs_dir}[/] into ChromaDB ({target_dir})...[/]",
        spinner="dots",
    ):
        try:
            _, chunk_count = ingest_knowledge_base(
                docs_dir=docs_dir,
                persist_dir=target_dir,
                settings=cfg,
            )
        except Exception as exc:
            err_console.print(f"[bold red]Ingestion Failed:[/] {exc}")
            raise typer.Exit(code=1) from exc

    summary_table = Table(title="RAG Ingestion Complete", box=box.ROUNDED)
    summary_table.add_column("Property", style="bold cyan")
    summary_table.add_column("Value", style="bold white")
    summary_table.add_row("Source Directory", str(docs_dir))
    summary_table.add_row("Persist Directory", str(target_dir))
    summary_table.add_row("Total Semantic Chunks", str(chunk_count))
    summary_table.add_row("Status", "[bold green]INDEXED SUCCESSFULLY[/]")
    console.print(summary_table)


@rag_app.command(name="eval")
def rag_eval_command(
    persist_dir: Annotated[
        Path | None,
        typer.Option(
            "--persist-dir",
            "-p",
            help="ChromaDB vectorstore directory to evaluate.",
        ),
    ] = None,
    top_k: Annotated[
        int,
        typer.Option(
            "--top-k",
            "-k",
            help="Number of retrieved chunks per query.",
        ),
    ] = 4,
) -> None:
    """Run benchmark evaluation suite over the RAG retriever (Hit Rate & MRR)."""
    cfg = get_settings()
    target_dir = persist_dir or cfg.chroma_persist_dir
    eval_settings = Settings(**{**cfg.model_dump(), "chroma_persist_dir": target_dir})

    with console.status(
        f"[bold cyan]Running 12-query threat intelligence RAG benchmark against {target_dir}...[/]",
        spinner="dots",
    ):
        try:
            retriever = KnowledgeRetriever(settings=eval_settings, top_k=top_k)
            report = evaluate_rag_retriever(retriever, top_k=top_k)
        except Exception as exc:
            err_console.print(f"[bold red]RAG Evaluation Failed:[/] {exc}")
            raise typer.Exit(code=1) from exc

    # Benchmark results table
    eval_table = Table(
        title="RAG Retrieval Benchmark Results",
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
    )
    eval_table.add_column("#", width=4)
    eval_table.add_column("Query / Threat Topic", style="white", width=42)
    eval_table.add_column("Target Technique", style="yellow", width=14)
    eval_table.add_column("Top Match Source", style="dim", width=28)
    eval_table.add_column("Hit", width=8)
    eval_table.add_column("Rank", width=6)

    for idx, res in enumerate(report.results, start=1):
        hit_badge = "[bold green]YES[/]" if res.is_hit else "[bold red]NO[/]"
        rr_str = f"{res.reciprocal_rank:.2f}" if res.is_hit else "-"
        top_match = res.matched_by or (
            res.retrieved_sources[0] if res.retrieved_sources else "None"
        )
        retrieved_tech = ", ".join(res.retrieved_techniques) or "N/A"
        eval_table.add_row(
            str(idx),
            res.question[:40] + ("..." if len(res.question) > 40 else ""),
            retrieved_tech,
            top_match[:26],
            hit_badge,
            rr_str,
        )

    console.print(eval_table)

    # Metrics Summary Panel
    mrr_style = "bold green" if report.mrr >= 0.7 else "bold yellow"
    hit_style = "bold green" if report.hit_rate >= 0.8 else "bold yellow"
    metrics_text = (
        f"[bold]Total Benchmark Questions:[/] {report.total_questions}\n"
        f"[bold]Successful Hits:[/] [{hit_style}]{report.hits} / {report.total_questions}[/]\n"
        f"[bold]Hit Rate:[/] [{hit_style}]{report.hit_rate * 100:.1f}%[/]\n"
        f"[bold]Mean Reciprocal Rank (MRR):[/] [{mrr_style}]{report.mrr:.3f}[/]"
    )
    console.print(
        Panel(
            metrics_text,
            title="[bold white on green] RAG RETRIEVAL EVALUATION METRICS [/]",
            border_style="green",
            box=box.ROUNDED,
        )
    )


@cache_app.command(name="clear")
def cache_clear_command() -> None:
    """Clear local telemetry and query diskcache."""
    cfg = get_settings()
    count = clear_local_cache(cfg.cache_dir)
    console.print(f"[bold green]✓ Cleared {count} cached objects from:[/] [cyan]{cfg.cache_dir}[/]")


@app.command(name="version")
def version_command() -> None:
    """Display threat-intel-agent version."""
    console.print(f"[bold cyan]threat-intel-agent[/] version [bold white]{__version__}[/]")


if __name__ == "__main__":
    app()
