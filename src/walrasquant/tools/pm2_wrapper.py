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
        click.echo(
            "Error: pm2 not found. Install it with: npm install -g pm2", err=True
        )
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


def _resolve_settings_attr(attr_path: str):
    """Traverse a dotted attribute path on the walrasquant settings object."""
    from walrasquant.constants import settings

    obj = settings
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    return obj


def _extract_log_filename(script_path: str) -> str | None:
    """Extract LogConfig filename from a Python script via regex."""
    try:
        src = Path(script_path).read_text(encoding="utf-8", errors="ignore")
        match = re.search(
            r'LogConfig\s*\(.*?filename\s*=\s*["\']([^"\']+)["\']',
            src,
            re.DOTALL,
        )
        if match:
            return match.group(1)
        match = re.search(
            r"LogConfig\s*\(.*?filename\s*=\s*settings\.([\w.]+)",
            src,
            re.DOTALL,
        )
        if match:
            return str(_resolve_settings_attr(match.group(1)))
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
        candidates = sorted(logs_dir.glob(f"{name}_????????.log"))
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


def _extract_config_field(script_path: str, field: str) -> str | None:
    """Extract a string field from Config(...) in a Python script via regex.

    Tries string literals first, then falls back to settings.<path>.<field>.
    """
    try:
        src = Path(script_path).read_text()
        match = re.search(
            rf'Config\s*\(.*?{field}\s*=\s*["\']([^"\']+)["\']',
            src,
            re.DOTALL,
        )
        if match:
            return match.group(1)
        match = re.search(
            rf"Config\s*\(.*?{field}\s*=\s*settings\.([\w.]+)",
            src,
            re.DOTALL,
        )
        if match:
            return str(_resolve_settings_attr(match.group(1)))
    except (OSError, PermissionError):
        pass
    return None


@cli.command("start")
@click.argument("script")
@click.option(
    "--strategy-id",
    "-s",
    default=None,
    help="Strategy identifier (extracted from script if omitted)",
)
@click.option(
    "--user-id",
    "-u",
    default=None,
    help="User identifier (extracted from script if omitted)",
)
def start_cmd(script: str, strategy_id: str | None, user_id: str | None):
    """Start a strategy script via PM2.

    The PM2 process name will be set to STRATEGY_ID.USER_ID.
    If --strategy-id or --user-id are omitted they are extracted from
    the Config(...) definition inside the script.

    Examples:\n
      wq start strategy/buy_and_sell.py\n
      wq start strategy/buy_and_sell.py -s buy_and_sell -u user_test\n
      wq start /abs/path/to/strategy.py --strategy-id arb --user-id alice
    """
    script_path = Path(script).resolve()
    if not script_path.exists():
        click.echo(f"Error: script '{script}' not found.", err=True)
        sys.exit(1)

    if strategy_id is None:
        strategy_id = _extract_config_field(str(script_path), "strategy_id")
        if strategy_id is None:
            click.echo(
                "Error: could not extract strategy_id from script. Pass it explicitly with -s.",
                err=True,
            )
            sys.exit(1)

    if user_id is None:
        user_id = _extract_config_field(str(script_path), "user_id")
        if user_id is None:
            click.echo(
                "Error: could not extract user_id from script. Pass it explicitly with -u.",
                err=True,
            )
            sys.exit(1)

    log_filename = _extract_log_filename(str(script_path))
    if log_filename is None:
        click.echo(
            "Error: could not find LogConfig(filename=...) in script. "
            "A log path is required to start a strategy.",
            err=True,
        )
        sys.exit(1)

    name = f"{strategy_id}.{user_id}"

    # Duplicate check
    processes = _pm2_jlist()
    if any(p.get("name") == name for p in processes):
        status = next(
            p.get("pm2_env", {}).get("status", "unknown")
            for p in processes
            if p.get("name") == name
        )
        click.echo(
            f"Error: PM2 process '{name}' already exists (status: {status}). "
            "Use 'wq restart' or 'wq delete' first.",
            err=True,
        )
        sys.exit(1)

    cmd = ["pm2", "start", str(script_path), "--name", name]
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


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
    table.add_column("Strategy ID", style="bold")
    table.add_column("User ID", style="bold")
    table.add_column("Status", width=10)
    table.add_column("PID", width=8)
    table.add_column("Log File", style="dim")

    for proc, _ in wq_procs:
        pm_id = str(proc.get("pm_id", "-"))
        name = proc.get("name", "")
        strategy_id, _, user_id = name.partition(".")
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

        table.add_row(pm_id, strategy_id, user_id or "-", status_str, pid, log_file)

    console.print(table)


@cli.command(
    "logs", context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
@click.argument("name")
@click.option(
    "-F",
    "--follow",
    is_flag=True,
    help="Live-tail mode (passes -F to hl, disables pager)",
)
@click.option(
    "-d",
    "--days",
    default=1,
    show_default=True,
    help="Include last N days of rotated files",
)
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

    try:
        os.execvp("hl", hl_cmd)
    except FileNotFoundError:
        click.echo(
            "Error: hl not found. Install it from: https://github.com/pamburus/hl",
            err=True,
        )
        sys.exit(1)


@cli.command("flush")
@click.argument("name")
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt.",
)
def flush_cmd(name: str, yes: bool):
    """Flush strategy log files for a PM2 process, or remove all logs.

    NAME can be a PM2 process ID, a process name (STRATEGY_ID.USER_ID),
    or the special keyword 'all' to delete every strategy log file.

    This operates on WalrasQuant strategy log files, not PM2 logs.

    Examples:\n
      wq flush buy_and_sell.alice\n
      wq flush 3\n
      wq flush all\n
      wq flush all --yes
    """
    processes = _pm2_jlist()

    if name == "all":
        # Collect log files from every known PM2 process
        log_files: list[Path] = []
        for proc in processes:
            log_base = _resolve_log_base(proc)
            if log_base is None:
                continue
            files = sorted(log_base.parent.glob(f"{log_base.name}_????????.log"))
            base_log = log_base.with_suffix(".log")
            if base_log.exists() and base_log not in files:
                files.insert(0, base_log)
            log_files.extend(files)

        if not log_files:
            click.echo("No strategy log files found.")
            return

        click.echo(f"Log files to remove ({len(log_files)} total):")
        for f in log_files:
            size = f.stat().st_size if f.exists() else 0
            click.echo(f"  {f}  ({size:,} bytes)")

        if not yes:
            click.confirm("\nDelete all listed files?", abort=True)

        removed, errors = 0, 0
        for f in log_files:
            try:
                f.unlink()
                removed += 1
            except OSError as exc:
                click.echo(f"Error removing {f}: {exc}", err=True)
                errors += 1

        click.echo(
            f"Removed {removed} file(s)." + (f" {errors} error(s)." if errors else "")
        )
        if errors:
            sys.exit(1)
        return

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

    # Find all rotated log files (any date); use exact 8-digit date pattern to avoid
    # matching files whose names share a common prefix (e.g. "app" matching "app_usdt_*")
    pattern = f"{log_base.name}_????????.log"
    log_files = sorted(log_base.parent.glob(pattern))
    # Also include the base log file without date suffix if it exists
    base_log = log_base.with_suffix(".log")
    if base_log.exists() and base_log not in log_files:
        log_files.insert(0, base_log)

    if not log_files:
        click.echo(f"No log files found matching '{log_base}*.log'.")
        return

    proc_name = proc.get("name", name)
    click.echo(f"Log files to flush for '{proc_name}':")
    for f in log_files:
        size = f.stat().st_size if f.exists() else 0
        click.echo(f"  {f}  ({size:,} bytes)")

    if not yes:
        click.confirm("\nTruncate all listed files?", abort=True)

    flushed, errors = 0, 0
    for f in log_files:
        try:
            f.write_bytes(b"")
            flushed += 1
        except OSError as exc:
            click.echo(f"Error flushing {f}: {exc}", err=True)
            errors += 1

    click.echo(
        f"Flushed {flushed} file(s)." + (f" {errors} error(s)." if errors else "")
    )
    if errors:
        sys.exit(1)


def _detect_backend(script_path: str) -> str:
    """Return 'postgresql' if the script uses PostgreSQL storage, else 'sqlite'."""
    try:
        src = Path(script_path).read_text(encoding="utf-8", errors="ignore")
        if re.search(r"StorageType\.POSTGRESQL|storage_backend.*POSTGRESQL", src, re.IGNORECASE):
            return "postgresql"
    except (OSError, PermissionError):
        pass
    return "sqlite"


def _resolve_db(proc: dict) -> tuple[str, str, str]:
    """Return (backend_type, db_path_or_empty, table_prefix) for a PM2 process."""
    pm2_env = proc.get("pm2_env", {})
    name = proc.get("name", "")
    strategy_id, _, user_id = name.partition(".")
    table_prefix = re.sub(r"[^a-zA-Z0-9_]", "_", f"{strategy_id}_{user_id}").lower()

    script_path = pm2_env.get("pm_exec_path", "")
    cwd = pm2_env.get("pm_cwd") or pm2_env.get("pm2_cwd") or ""
    cwd_path = Path(cwd) if cwd else Path.cwd()

    backend = _detect_backend(script_path)

    if backend == "sqlite":
        db_path_str = _extract_config_field(script_path, "db_path") or ".keys/cache.db"
        db_path = Path(db_path_str)
        if not db_path.is_absolute():
            db_path = cwd_path / db_path
        return "sqlite", str(db_path), table_prefix

    return "postgresql", "", table_prefix


def _query_db(backend: str, db_path: str, table_prefix: str, query: str, params: tuple = ()):
    """Execute a SELECT and return rows."""
    if backend == "sqlite":
        import sqlite3
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(query, params)
            return cur.fetchall()
        finally:
            conn.close()
    else:
        import psycopg2
        from walrasquant.constants import get_postgresql_config
        conn = psycopg2.connect(**get_postgresql_config())
        try:
            cur = conn.cursor()
            cur.execute(query, params)
            return cur.fetchall()
        finally:
            conn.close()


@cli.command("pos")
@click.argument("name")
def pos_cmd(name: str):
    """Show open positions for a strategy process.

    NAME can be a PM2 process name (STRATEGY_ID.USER_ID) or numeric PM2 id.

    Examples:\n
      wq pos buy_and_sell.alice\n
      wq pos 0
    """
    import json as _json

    processes = _pm2_jlist()
    proc = _find_process(processes, name)
    if proc is None:
        click.echo(f"Error: PM2 process '{name}' not found.", err=True)
        click.echo(f"Available: {[p.get('name') for p in processes]}", err=True)
        sys.exit(1)

    backend, db_path, table_prefix = _resolve_db(proc)

    if backend == "sqlite" and not Path(db_path).exists():
        click.echo(f"Error: SQLite database not found: {db_path}", err=True)
        sys.exit(1)

    query = f"SELECT symbol, exchange, side, amount, data FROM {table_prefix}_positions"
    try:
        rows = _query_db(backend, db_path, table_prefix, query)
    except Exception as e:
        if "no such table" in str(e).lower() or "does not exist" in str(e).lower():
            click.echo("No open positions found.")
            return
        click.echo(f"Error querying positions: {e}", err=True)
        sys.exit(1)

    # Filter out flat/null positions
    open_rows = [r for r in rows if r[2] and r[2].upper() not in ("FLAT", "NONE", "NULL")]
    if not open_rows:
        click.echo("No open positions found.")
        return

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Symbol", style="bold")
    table.add_column("Exchange")
    table.add_column("Side", width=6)
    table.add_column("Amount", justify="right")
    table.add_column("Entry Price", justify="right")
    table.add_column("Unrealized PnL", justify="right")
    table.add_column("Realized PnL", justify="right")

    for symbol, exchange, side, amount, data in open_rows:
        try:
            if isinstance(data, memoryview):
                raw = bytes(data)
            elif isinstance(data, str):
                raw = data.encode()
            else:
                raw = data
            d = _json.loads(raw)
            entry_price = f"{d.get('entry_price', 0):.6g}"
            unrealized = f"{d.get('unrealized_pnl', 0):.4f}"
            realized = f"{d.get('realized_pnl', 0):.4f}"
        except Exception:
            entry_price = unrealized = realized = "?"

        side_upper = (side or "").upper()
        if side_upper in ("LONG", "BUY"):
            side_str = f"[green]{side_upper}[/green]"
        elif side_upper in ("SHORT", "SELL"):
            side_str = f"[red]{side_upper}[/red]"
        else:
            side_str = side_upper

        table.add_row(symbol, exchange or "", side_str, amount or "", entry_price, unrealized, realized)

    console.print(table)


@cli.command("bal")
@click.argument("name")
@click.option("--all", "-a", "show_all", is_flag=True, help="Show zero-balance assets too.")
def bal_cmd(name: str, show_all: bool):
    """Show non-zero account balances for a strategy process.

    NAME can be a PM2 process name (STRATEGY_ID.USER_ID) or numeric PM2 id.
    Zero-balance assets are hidden by default; use --all to show them.

    Examples:\n
      wq bal buy_and_sell.alice\n
      wq bal 0\n
      wq bal 0 --all
    """
    from decimal import Decimal

    processes = _pm2_jlist()
    proc = _find_process(processes, name)
    if proc is None:
        click.echo(f"Error: PM2 process '{name}' not found.", err=True)
        click.echo(f"Available: {[p.get('name') for p in processes]}", err=True)
        sys.exit(1)

    backend, db_path, table_prefix = _resolve_db(proc)

    if backend == "sqlite" and not Path(db_path).exists():
        click.echo(f"Error: SQLite database not found: {db_path}", err=True)
        sys.exit(1)

    query = (
        f"SELECT asset, account_type, free, locked FROM {table_prefix}_balances "
        "ORDER BY account_type, asset"
    )
    try:
        rows = _query_db(backend, db_path, table_prefix, query)
    except Exception as e:
        if "no such table" in str(e).lower() or "does not exist" in str(e).lower():
            click.echo("No balance data found.")
            return
        click.echo(f"Error querying balances: {e}", err=True)
        sys.exit(1)

    if not rows:
        click.echo("No balance data found.")
        return

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Asset", style="bold")
    table.add_column("Account Type")
    table.add_column("Free", justify="right")
    table.add_column("Locked", justify="right")
    table.add_column("Total", justify="right")

    for asset, account_type, free_str, locked_str in rows:
        try:
            free = Decimal(free_str or "0")
            locked = Decimal(locked_str or "0")
            total = free + locked
        except Exception:
            free = locked = total = Decimal("0")

        if not show_all and total == Decimal("0"):
            continue

        table.add_row(
            asset or "",
            account_type or "",
            str(free),
            str(locked),
            str(total),
        )

    console.print(table)


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
cli.add_command(logs_cmd, name="log")
cli.add_command(flush_cmd, name="clear")


def main():
    """Entry point for wq command."""
    cli()


if __name__ == "__main__":
    main()
