import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


def _pm2_jlist() -> list[dict]:
    """Run pm2 jlist and return parsed JSON."""
    try:
        result = subprocess.run(
            ["pm2", "jlist"],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except FileNotFoundError:
        click.echo("Error: pm2 not found. Install it with: npm install -g pm2", err=True)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        click.echo(f"Error running pm2 jlist: {e.stderr}", err=True)
        sys.exit(1)
    except json.JSONDecodeError as e:
        click.echo(f"Error parsing pm2 jlist output: {e}", err=True)
        sys.exit(1)


def _find_process(processes: list[dict], name: str) -> dict | None:
    """Find a PM2 process by name or numeric pm_id."""
    # Numeric ID lookup
    if name.isdigit():
        pm_id = int(name)
        for proc in processes:
            if proc.get("pm_id") == pm_id:
                return proc
        return None

    matches = [p for p in processes if p.get("name") == name]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    # Multiple matches: prefer online
    online = [p for p in matches if p.get("pm2_env", {}).get("status") == "online"]
    return online[0] if online else matches[0]


def _extract_log_filename(script_path: str) -> str | None:
    """Extract LogConfig filename from a Python script via regex."""
    try:
        src = Path(script_path).read_text()
        match = re.search(
            r'LogConfig\s*\(.*?filename\s*=\s*["\']([^"\']+)["\']',
            src,
            re.DOTALL,
        )
        if match:
            return match.group(1)
    except (OSError, PermissionError):
        pass
    return None


def _resolve_log_base(proc: dict) -> Path | None:
    """
    Resolve the base log path (without date suffix) for a PM2 process.

    Returns a Path like /path/to/cwd/logs/app (without extension),
    or None if it cannot be determined.
    """
    pm2_env = proc.get("pm2_env", {})
    cwd = pm2_env.get("pm_cwd") or pm2_env.get("pm2_cwd") or ""
    script_path = pm2_env.get("pm_exec_path", "")

    cwd_path = Path(cwd) if cwd else Path.cwd()

    # Try extracting from script source
    if script_path and Path(script_path).exists():
        filename = _extract_log_filename(script_path)
        if filename:
            log_path = Path(filename)
            if not log_path.is_absolute():
                log_path = cwd_path / log_path
            # Strip extension to get base (e.g. logs/app from logs/app.log)
            return log_path.with_suffix("")

    # Fallback: scan cwd/logs/ for *{name}*.log
    name = proc.get("name", "")
    logs_dir = cwd_path / "logs"
    if logs_dir.is_dir():
        candidates = sorted(logs_dir.glob(f"*{name}*.log"))
        if candidates:
            # Take stem of the latest file, strip date suffix (_YYYYMMDD)
            stem = candidates[-1].stem
            stem = re.sub(r"_\d{8}$", "", stem)
            return logs_dir / stem

    return None


def _date_rotated_files(log_base: Path, days: int) -> list[Path]:
    """
    Find date-rotated log files matching {log_base}_YYYYMMDD.log
    within the last `days` days (counting today).
    """
    today = date.today()
    cutoff = today - timedelta(days=days - 1)

    pattern = f"{log_base.name}_*.log"
    candidates = sorted(log_base.parent.glob(pattern))

    result = []
    for path in candidates:
        m = re.search(r"_(\d{8})\.log$", path.name)
        if m:
            try:
                file_date = date(
                    int(m.group(1)[:4]),
                    int(m.group(1)[4:6]),
                    int(m.group(1)[6:8]),
                )
                if cutoff <= file_date <= today:
                    result.append(path)
            except ValueError:
                pass

    return result


def _proc_log_summary(proc: dict) -> str:
    """Return a short log path string for display in list."""
    log_base = _resolve_log_base(proc)
    if log_base is None:
        return "<unknown>"
    today_str = date.today().strftime("%Y%m%d")
    candidate = log_base.parent / f"{log_base.name}_{today_str}.log"
    if candidate.exists():
        return str(candidate)
    # Show pattern if today's file doesn't exist yet
    return str(log_base.parent / f"{log_base.name}_*.log")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli():
    """wq: PM2 + hl wrapper for WalrasQuant strategies."""
    pass


@cli.command("list")
def list_cmd():
    """List PM2 processes with resolved log file paths."""
    processes = _pm2_jlist()
    if not processes:
        click.echo("No WalrasQuant PM2 processes found.")
        return

    wq_procs = [(proc, _resolve_log_base(proc)) for proc in processes]
    wq_procs = [(proc, lb) for proc, lb in wq_procs if lb is not None]

    if not wq_procs:
        click.echo("No WalrasQuant PM2 processes found.")
        return

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=5)
    table.add_column("Name", style="bold")
    table.add_column("Status", width=10)
    table.add_column("PID", width=8)
    table.add_column("Log File", style="dim")

    for proc, _ in wq_procs:
        pm_id = str(proc.get("pm_id", "-"))
        name = proc.get("name", "")
        pm2_env = proc.get("pm2_env", {})
        status = pm2_env.get("status", "unknown")
        pid = str(proc.get("pid", "-"))
        log_file = _proc_log_summary(proc)

        if status == "online":
            status_str = f"[green]{status}[/green]"
        elif status == "errored":
            status_str = f"[red]{status}[/red]"
        else:
            status_str = f"[yellow]{status}[/yellow]"

        table.add_row(pm_id, name, status_str, pid, log_file)

    console.print(table)


@cli.command("logs", context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("name")
@click.option("-F", "--follow", is_flag=True, help="Live-tail mode (passes -F to hl, disables pager)")
@click.option("-d", "--days", default=1, show_default=True, help="Include last N days of rotated files")
@click.pass_context
def logs_cmd(ctx: click.Context, name: str, follow: bool, days: int):
    """View logs for a PM2 process using hl.

    All unrecognised options are forwarded verbatim to hl.

    Examples:\n
      wq logs buy_and_sell\n
      wq logs buy_and_sell -F\n
      wq logs buy_and_sell -d 3\n
      wq logs buy_and_sell -l e\n
      wq logs buy_and_sell -q 'level > info'\n
      wq logs buy_and_sell --since -1h --until now\n
      wq logs buy_and_sell -f component=tsdb
    """
    processes = _pm2_jlist()
    proc = _find_process(processes, name)
    if proc is None:
        click.echo(f"Error: PM2 process '{name}' not found.", err=True)
        click.echo(f"Available: {[p.get('name') for p in processes]}", err=True)
        sys.exit(1)

    log_base = _resolve_log_base(proc)
    if log_base is None:
        click.echo(
            f"Error: Could not resolve log path for '{name}'.\n"
            "Make sure the script contains LogConfig(filename=...) or has logs in cwd/logs/.",
            err=True,
        )
        sys.exit(1)

    log_files = _date_rotated_files(log_base, days)
    if not log_files:
        click.echo(
            f"No log files found matching '{log_base}_*.log' within the last {days} day(s).",
            err=True,
        )
        sys.exit(1)

    hl_cmd: list[str] = ["hl"]

    if follow:
        hl_cmd.append("-F")
    elif days > 1:
        hl_cmd.append("-s")

    # Forward all unrecognised args/options directly to hl
    hl_cmd.extend(ctx.args)

    hl_cmd.extend(str(f) for f in log_files)

    os.execvp("hl", hl_cmd)


@cli.command("stop")
@click.argument("name")
def stop_cmd(name: str):
    """Stop a PM2 process."""
    subprocess.run(["pm2", "stop", name])


@cli.command("restart")
@click.argument("name")
def restart_cmd(name: str):
    """Restart a PM2 process."""
    subprocess.run(["pm2", "restart", name])


@cli.command("delete")
@click.argument("name")
def delete_cmd(name: str):
    """Delete a PM2 process."""
    subprocess.run(["pm2", "delete", name])


cli.add_command(list_cmd, name="ls")


def main():
    """Entry point for wq command."""
    cli()


if __name__ == "__main__":
    main()
