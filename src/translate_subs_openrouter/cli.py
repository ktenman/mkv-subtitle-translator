from __future__ import annotations

import glob
import json
import logging
import os
import subprocess
import urllib.error
import urllib.request
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer
from packaging.version import Version
from rich.console import Console
from rich.table import Table

from translate_subs_openrouter.mkv import extract_best_subtitle_from_mkv, merge_subtitles_into_mkv
from translate_subs_openrouter.models import DEFAULT_MODEL, SUBTITLE_MODELS
from translate_subs_openrouter.translator import OpenRouterTranslator, deduplicate_subtitles

logger = logging.getLogger(__name__)

GITHUB_REPO = "ktenman/translate-subs-openrouter"

app = typer.Typer(
    name="translate-subs-openrouter",
    help="Translate SRT subtitles to Estonian using OpenRouter (200+ models).",
    add_completion=False,
)
console = Console()


def _check_and_upgrade(current: str) -> None:
    """Check GitHub for latest release and auto-upgrade if outdated."""
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            latest = json.loads(resp.read())["tag_name"].lstrip("v")
    except urllib.error.HTTPError as e:
        if e.code == 403:
            logger.warning("GitHub API rate limit exceeded")
        else:
            logger.debug("Update check HTTP error %s", e.code, exc_info=True)
        return
    except Exception:
        logger.debug("Failed to check for updates", exc_info=True)
        return

    if Version(current) >= Version(latest):
        logger.info("translate-subs-openrouter is up to date (v%s)", current)
        return

    logger.info("New version available: v%s (current: v%s)", latest, current)
    console.print(f"[yellow]Upgrading v{current} -> v{latest}...[/yellow]")
    upgrade_commands = [
        ["uv", "tool", "upgrade", "translate-subs-openrouter"],
        ["uv", "pip", "install", "--upgrade", f"git+https://github.com/{GITHUB_REPO}.git"],
    ]
    for cmd in upgrade_commands:
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            console.print(f"[green]Upgraded to v{latest}. Please re-run your command.[/green]")
            raise typer.Exit(0)
        except typer.Exit:
            raise
        except Exception:
            logger.debug("Upgrade with '%s' failed", " ".join(cmd), exc_info=True)

    logger.warning("All upgrade methods failed")
    console.print(
        "[yellow]Auto-upgrade failed. Run manually:[/yellow]\n"
        "  uv tool upgrade translate-subs-openrouter"
    )


def _validate_model(value: str) -> str:
    if value not in SUBTITLE_MODELS:
        raise typer.BadParameter(f"Unknown model '{value}'. Run --list-models to see options.")
    return value


def list_models() -> None:
    """Print available models grouped by tier."""
    console.print("\n[bold]Available Models for Subtitle Translation[/bold]")
    for tier in ("premium", "value", "budget"):
        tier_models = {k: v for k, v in SUBTITLE_MODELS.items() if v["tier"] == tier}
        if not tier_models:
            continue
        table = Table(title=tier.upper())
        table.add_column("Key", style="cyan")
        table.add_column("Name")
        table.add_column("$/1M tokens", justify="right")
        table.add_column("Best for")
        for key, config in tier_models.items():
            cost = config["cost_per_1m_input"] + config["cost_per_1m_output"]
            table.add_row(key, config["name"], f"${cost:.2f}", ", ".join(config["recommended_for"]))
        console.print(table)
    console.print(f"\nDefault: [green]{DEFAULT_MODEL}[/green] (best quality/cost balance)")


def estimate_cost(file_path: str, model: str = DEFAULT_MODEL) -> None:
    """Estimate translation cost for a file (supports .srt and .mkv)."""
    srt_path = file_path
    temp_extracted = False
    if file_path.lower().endswith(".mkv"):
        console.print("Extracting subtitles from MKV for estimation...")
        srt_path = extract_best_subtitle_from_mkv(file_path)
        if not srt_path:
            console.print("[red]Error: Could not extract subtitles from MKV[/red]")
            return
        temp_extracted = True

    translator = OpenRouterTranslator("dummy", model)
    subtitles = translator.read_srt(srt_path)
    subtitles = deduplicate_subtitles(subtitles)

    if temp_extracted and os.path.exists(srt_path):
        os.remove(srt_path)

    avg_input_tokens = 150
    avg_output_tokens = 30
    total_input = len(subtitles) * avg_input_tokens
    total_output = len(subtitles) * avg_output_tokens

    config = SUBTITLE_MODELS.get(model, SUBTITLE_MODELS[DEFAULT_MODEL])
    input_cost = (total_input / 1_000_000) * config["cost_per_1m_input"]
    output_cost = (total_output / 1_000_000) * config["cost_per_1m_output"]
    total_cost = input_cost + output_cost

    console.print(f"\n[bold]Cost Estimate for {Path(file_path).name}[/bold]")
    console.print(f"Subtitles: {len(subtitles)}")
    console.print(f"Model: {config['name']}")
    console.print(f"Estimated tokens: ~{total_input:,} in / ~{total_output:,} out")
    console.print(f"Estimated cost: [green]${total_cost:.4f}[/green]")

    table = Table(title="Comparison across models")
    table.add_column("Model", style="cyan")
    table.add_column("Est. cost", justify="right")
    for key, cfg in SUBTITLE_MODELS.items():
        ic = (total_input / 1_000_000) * cfg["cost_per_1m_input"]
        oc = (total_output / 1_000_000) * cfg["cost_per_1m_output"]
        table.add_row(key, f"${ic + oc:.4f}")
    console.print(table)


@app.command()
def _main(
    path: Annotated[str, typer.Argument(help="Directory or file to translate")] = ".",
    file: Annotated[
        str | None, typer.Option("-f", "--file", help="Translate a specific file")
    ] = None,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", help="OpenRouter API key (or set OPENROUTER_API_KEY)"),
    ] = None,
    model: Annotated[
        str,
        typer.Option(
            "--model",
            help=f"Model to use (default: {DEFAULT_MODEL}). See --list-models.",
            callback=_validate_model,
        ),
    ] = DEFAULT_MODEL,
    list_models_flag: Annotated[
        bool, typer.Option("--list-models", help="List available models")
    ] = False,
    estimate: Annotated[
        str | None, typer.Option("--estimate", help="Estimate cost for a file")
    ] = None,
    no_merge: Annotated[
        bool, typer.Option("--no-merge", help="Do not merge subtitles back into MKV")
    ] = False,
    no_backup: Annotated[
        bool, typer.Option("--no-backup", help="Do not create backup when merging")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Force retranslation even if output exists")
    ] = False,
    chunk_size: Annotated[
        int, typer.Option("--chunk-size", help="Chunk size for parallel processing")
    ] = 50,
    max_workers: Annotated[int, typer.Option("--max-workers", help="Max parallel workers")] = 8,
) -> None:
    """Translate subtitles to Estonian using OpenRouter (200+ models)."""
    current_version = version("translate-subs-openrouter")
    console.print(f"[dim]translate-subs-openrouter v{current_version}[/dim]")
    _check_and_upgrade(current_version)

    if list_models_flag:
        list_models()
        raise typer.Exit(0)

    if estimate:
        if not os.path.exists(estimate):
            console.print(f"[red]Error: File not found: {estimate}[/red]")
            raise typer.Exit(1)
        estimate_cost(estimate, model)
        raise typer.Exit(0)

    resolved_api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not resolved_api_key:
        console.print("[red]Error: OpenRouter API key required[/red]")
        console.print("Set via --api-key or OPENROUTER_API_KEY environment variable")
        console.print("Get your key at: https://openrouter.ai/keys")
        raise typer.Exit(1)

    files_to_translate: list[str] = []
    mkv_to_subs_map: dict[str, list[str]] = {}

    if file:
        if os.path.exists(file):
            if file.endswith(".srt"):
                files_to_translate.append(file)
            elif file.endswith(".mkv"):
                extracted = extract_best_subtitle_from_mkv(file)
                if extracted:
                    files_to_translate.append(extracted)
                    mkv_to_subs_map[file] = [extracted.replace(".extracted.srt", ".et.srt")]
                else:
                    console.print("[red]Error: Could not extract subtitles[/red]")
                    raise typer.Exit(1)
        else:
            console.print(f"[red]Error: File not found: {file}[/red]")
            raise typer.Exit(1)
    else:
        if not os.path.isdir(path):
            console.print(f"[red]Error: Invalid directory: {path}[/red]")
            raise typer.Exit(1)

        srt_files = glob.glob(os.path.join(path, "*.extracted.srt"))

        if srt_files and not force:
            files_to_translate = srt_files
            for srt in srt_files:
                mkv = srt.replace(".extracted.srt", ".mkv")
                if os.path.exists(mkv):
                    mkv_to_subs_map[mkv] = [srt.replace(".extracted.srt", ".et.srt")]
        else:
            mkv_files = glob.glob(os.path.join(path, "*.mkv"))
            for mkv in mkv_files:
                extracted = extract_best_subtitle_from_mkv(mkv)
                if extracted:
                    files_to_translate.append(extracted)
                    mkv_to_subs_map[mkv] = [extracted.replace(".extracted.srt", ".et.srt")]

    if not files_to_translate:
        console.print("No files to translate")
        raise typer.Exit(0)

    for input_file in files_to_translate:
        output_file = input_file.replace(".extracted.srt", ".et.srt")
        if ".et.srt" not in output_file:
            output_file = output_file.replace(".srt", ".et.srt")

        if not force and os.path.exists(output_file):
            print(f"\nSkipping {Path(input_file).name} - output exists")
            continue

        print(f"\nProcessing: {Path(input_file).name}")

        translator = OpenRouterTranslator(resolved_api_key, model)
        subtitles = translator.read_srt(input_file)
        subtitles = deduplicate_subtitles(subtitles)

        print(f"Found {len(subtitles)} unique subtitles")

        types: dict[str, int] = {}
        for s in subtitles:
            t = s.subtitle_type.value if s.subtitle_type else "unknown"
            types[t] = types.get(t, 0) + 1

        print("Subtitle types:")
        for t, count in types.items():
            print(f"  {t}: {count} ({count / len(subtitles) * 100:.1f}%)")

        translated = translator.translate_subtitles(
            subtitles, chunk_size=chunk_size, max_workers=max_workers
        )

        translator.write_srt(translated, output_file)
        print(f"✅ Saved to: {output_file}")

    if not no_merge and mkv_to_subs_map:
        print(f"\n{'=' * 60}")
        print("MERGING SUBTITLES INTO MKV FILES")
        print(f"{'=' * 60}")

        for mkv, subs in mkv_to_subs_map.items():
            existing_subs = [s for s in subs if os.path.exists(s)]
            if existing_subs:
                merge_subtitles_into_mkv(mkv, existing_subs, backup=not no_backup)

    print(f"\n{'=' * 60}")
    print("ALL TRANSLATIONS COMPLETE")
    print(f"{'=' * 60}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
