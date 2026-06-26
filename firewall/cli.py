"""``firewall`` command-line entry point.

Subcommands::

    firewall config init|show|path
    firewall start [--mode host|docker]
    firewall stop
    firewall panel
    firewall scan <skill_dir>          # L0 static scan
    firewall watch <skill_dir>         # L2 verdict from a stored log
    firewall skills                    # list discovered skills
    firewall hook <agent>              # print env-vars to route an agent through the proxy

Logic lives in ``firewall.runtime`` and ``firewall.gate``; policy in
``~/.config/firewall/config.toml``. The config stores the NAME of the env
var holding the API key, never the key itself.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from firewall import __version__
from firewall.config import (
    Config,
    DEFAULT_CONFIG_TOML,
    config_path,
    init_default,
    load_config,
    state_dir,
)
from firewall.runtime.events import EventEmitter
from firewall.runtime.firewall import analyze_iar, build_intent_envelope


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Runtime behavioural firewall for Agent Skills.",
)
config_app = typer.Typer(help="Inspect or initialise ~/.config/firewall/config.toml")
app.add_typer(config_app, name="config")

console = Console()


# ---------------------------------------------------------------- helpers
def _load_or_die() -> Config:
    p = config_path()
    if not p.exists():
        init_default(p)
        console.print(f"[yellow]no config found — wrote default to[/yellow] {p}")
    return load_config(p)


def _check_api_key(cfg: Config) -> None:
    env = cfg.driver.api_key_env
    if not os.environ.get(env):
        console.print(
            f"[red]${env} is not set[/red] — "
            f"`export {env}=...` and retry, or edit {config_path()}"
        )
        raise typer.Exit(code=2)


# ------------------------------------------------------------------ root
@app.callback(invoke_without_command=True)
def root(version: bool = typer.Option(False, "--version", "-V")) -> None:
    if version:
        console.print(f"firewall {__version__}")
        raise typer.Exit()


# ----------------------------------------------------------------- config
@config_app.command("init")
def config_init(force: bool = typer.Option(False, "--force", "-f")) -> None:
    """Write the default config.toml (no-op if it exists, unless --force)."""
    p = init_default(overwrite=force)
    console.print(f"wrote [bold]{p}[/bold]")


@config_app.command("show")
def config_show() -> None:
    """Print the resolved configuration (after defaults applied)."""
    cfg = _load_or_die()
    t = Table(title=f"firewall config — {config_path()}", show_lines=True)
    t.add_column("section"); t.add_column("key"); t.add_column("value")
    def row(sect, key, val):
        t.add_row(sect, key, str(val))
    for k in ("provider", "model", "base_url", "api_key_env"):
        row("driver", k, getattr(cfg.driver, k))
    api_set = "yes" if os.environ.get(cfg.driver.api_key_env) else "[red]no[/red]"
    row("driver", f"${cfg.driver.api_key_env}", api_set)
    row("policy", "mode", cfg.policy.mode)
    row("egress", "allow_hosts", ", ".join(cfg.egress.allow_hosts[:5]) + " ...")
    row("egress", "deny_hosts", ", ".join(cfg.egress.deny_hosts[:5]) + " ...")
    row("secrets", "secret_paths", ", ".join(cfg.secrets.secret_paths[:5]))
    row("state", "events_path", cfg.state.events_path)
    console.print(t)


@config_app.command("path")
def config_path_cmd() -> None:
    """Print the config file path (shell-substitution-safe)."""
    typer.echo(str(config_path()))


@config_app.command("mode")
def config_mode(
    mode: str = typer.Argument(..., help="strict | balanced | observe"),
) -> None:
    """Set policy.mode in the TOML. The running proxy picks it up on next request."""
    valid = {"strict", "balanced", "observe"}
    if mode not in valid:
        console.print(f"[red]mode must be one of {', '.join(sorted(valid))}[/red]")
        raise typer.Exit(2)
    p = config_path()
    if not p.exists():
        init_default(p)
    import re
    text = p.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r'(?m)^(mode\s*=\s*)"(strict|balanced|observe)"',
        f'\\1"{mode}"', text, count=1)
    if n == 0:
        if "[policy]" in new_text:
            new_text = re.sub(
                r"(\[policy\][^\[]*)",
                lambda m: m.group(1).rstrip() + f'\nmode = "{mode}"\n\n',
                new_text, count=1)
        else:
            new_text += f'\n[policy]\nmode = "{mode}"\n'
    p.write_text(new_text, encoding="utf-8")
    console.print(f"policy.mode = [bold]{mode}[/bold]")


# ------------------------------------------------------------------ scan
@app.command("scan")
def scan(
    skill_dir: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True),
) -> None:
    """One-shot L0 static scan on a skill directory."""
    from firewall.gate.static_scanner import scan_skill_dir
    findings = scan_skill_dir(skill_dir, _load_or_die())
    if not findings:
        console.print(f"[green]{skill_dir.name}: NONE[/green]  (no static findings)")
        return
    t = Table(title=f"static findings — {skill_dir}")
    t.add_column("severity"); t.add_column("rule"); t.add_column("evidence")
    for f in findings:
        t.add_row(f.severity, f.rule, f.evidence[:80])
    console.print(t)


# ------------------------------------------------------------------ watch
@app.command("watch")
def watch(
    skill_dir: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    answer: str = typer.Option("", "--answer", help="agent's final answer (for tie-breaker)"),
    log_file: Path | None = typer.Option(None, "--log-file", help="proxy/canary log to ingest"),
) -> None:
    """Score a single skill run from a stored log (offline replay of the live proxy)."""
    from firewall.skills.discover import load_skill
    from firewall.runtime.supervisor import parse_line, evidence_from_events

    cfg = _load_or_die()
    sk = load_skill(skill_dir)
    if sk is None:
        console.print(f"[red]no SKILL.md in {skill_dir}[/red]")
        raise typer.Exit(code=2)
    events = []
    if log_file and log_file.exists():
        for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
            ev = parse_line(line)
            if ev is not None:
                events.append(ev)
    evidence = evidence_from_events(events, answer=answer)
    envelope = build_intent_envelope(sk.to_intent())
    verdict = analyze_iar(evidence, envelope, cfg)
    emitter = EventEmitter(cfg.state.events_path)
    emitter.emit(
        "verdict",
        skill=sk.name,
        verdict=verdict.verdict,
        score=verdict.score,
        reason=", ".join(verdict.confirmations or verdict.divergences)[:80],
        confirmations=verdict.confirmations,
        divergences=verdict.divergences,
    )
    color = {"benign": "green", "suspicious": "yellow", "malicious": "red"}[verdict.verdict]
    console.print(
        f"[{color}]{verdict.verdict.upper()}[/{color}] "
        f"score={verdict.score}  skill={sk.name}"
    )
    if verdict.confirmations:
        console.print(f"  confirmations: {', '.join(verdict.confirmations)}")
    if verdict.divergences:
        console.print(f"  divergences:   {', '.join(verdict.divergences)}")
    if verdict.containment:
        console.print(f"  containment:   {', '.join(verdict.containment)}  (not in verdict)")


# ----------------------------------------------------------------- start
@app.command("start")
def start(
    mode: str = typer.Option("host", "--mode", "-m", help="host | docker"),
    detach: bool = typer.Option(False, "--detach", "-d"),
) -> None:
    """Start the firewall.

    --mode host:   run egress proxy + canary as host processes (no docker).
    --mode docker: bring up firewall/docker/compose.yml.
    """
    cfg = _load_or_die()
    if mode == "docker":
        compose = Path(__file__).parent / "docker" / "compose.yml"
        if not compose.exists():
            console.print(f"[red]compose.yml not found at {compose}[/red]")
            raise typer.Exit(code=2)
        cmd = ["docker", "compose", "-f", str(compose), "up"]
        if detach:
            cmd.append("-d")
        console.print(f"[bold]$[/bold] {shlex.join(cmd)}")
        subprocess.run(cmd, check=False)
        return

    _check_api_key(cfg)
    Path(cfg.state.events_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    emitter = EventEmitter(cfg.state.events_path)

    # Actually launch the egress proxy (8080) and canary (8088) as background
    # threads in this process. Previously this command only emitted an info
    # event and idled — agents pointed at HTTP_PROXY=127.0.0.1:8080 found
    # nothing listening. Now `firewall start` does what it says.
    import threading
    from firewall.runtime import egress_proxy as _ep
    from firewall.runtime import canary as _cn
    proxy_thread = threading.Thread(
        target=_ep.serve, args=("127.0.0.1", 8080, cfg), daemon=True, name="egress-proxy")
    canary_thread = threading.Thread(
        target=_cn.serve, args=("127.0.0.1", 8088, cfg), daemon=True, name="canary")
    proxy_thread.start()
    canary_thread.start()

    emitter.emit("info", message="firewall started (host mode)",
                 model=cfg.driver.model, policy=cfg.policy.mode)
    console.print(
        f"[green]firewall running (host mode)[/green]\n"
        f"  proxy   127.0.0.1:8080   policy={cfg.policy.mode}\n"
        f"  canary  127.0.0.1:8088\n"
        f"  events  {cfg.state.events_path}\n"
        f"open another terminal and run [b]firewall panel[/b] to watch."
    )
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        emitter.emit("info", message="firewall stopped")
        console.print("\nstopped.")


# ------------------------------------------------------------------ stop
@app.command("stop")
def stop() -> None:
    """``docker compose down`` if a docker run is up."""
    compose = Path(__file__).parent / "docker" / "compose.yml"
    if not compose.exists():
        console.print("nothing to stop in host mode (Ctrl-C the `start` process).")
        return
    cmd = ["docker", "compose", "-f", str(compose), "down"]
    console.print(f"[bold]$[/bold] {shlex.join(cmd)}")
    subprocess.run(cmd, check=False)


# ----------------------------------------------------------------- panel
@app.command("panel")
def panel(
    web: bool = typer.Option(False, "--web", help="serve the browser panel instead of the terminal TUI"),
    port: int = typer.Option(8090, "--port", help="port for the browser panel"),
    no_open: bool = typer.Option(False, "--no-open", help="don't auto-open the browser"),
) -> None:
    """Live panel of passed/blocked + session + API usage.

    Default is a terminal TUI. `--web` serves the same view as a local
    browser page (both read the same events.jsonl).
    """
    cfg = _load_or_die()
    if web:
        from firewall.panel.web import serve_web
        serve_web(cfg.state.events_path, port=port, open_browser=not no_open)
    else:
        from firewall.panel.tui import run_panel
        run_panel(cfg.state.events_path, cfg)


# ------------------------------------------------------------------ bench
@app.command("bench")
def bench(
    skills_root: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True,
                                       resolve_path=True, help="folder of SKILL.md dirs"),
    log_dir: Path = typer.Option(None, "--log-dir", help="folder of per-skill NAME.log files for L2 replay"),
    out: Path = typer.Option(None, "--out", "-o", help="write CSV here (default: stdout)"),
) -> None:
    """Batch-scan a folder of skills and print one CSV row per skill.

    Runs L0 static scan on every skill, and (if --log-dir has a matching
    NAME.log) replays it through the L2 IAR verifier. Columns:
    skill, static_severity, runtime_verdict, runtime_score, reason.
    """
    import csv as _csv
    from firewall.gate.static_scanner import scan_skill_dir
    from firewall.runtime.firewall import analyze_iar, build_intent_envelope
    from firewall.runtime.supervisor import evidence_from_events, parse_line
    from firewall.skills.discover import load_skill

    cfg = _load_or_die()
    fh = out.open("w") if out else sys.stdout
    w = _csv.writer(fh)
    w.writerow(["skill", "static_severity", "runtime_verdict", "runtime_score", "reason"])
    for child in sorted(skills_root.iterdir()):
        if not child.is_dir():
            continue
        sk = load_skill(child)
        if sk is None:
            continue
        static = scan_skill_dir(child, cfg)
        static_sev = static[0].severity if static else "NONE"
        verdict, score, reason = "—", 0, "no log"
        if log_dir:
            lp = log_dir / f"{sk.name}.log"
            if lp.exists():
                events = [e for e in (parse_line(x) for x in lp.read_text().splitlines()) if e]
                v = analyze_iar(evidence_from_events(events),
                                build_intent_envelope(sk.to_intent()), cfg)
                verdict, score = v.verdict, v.score
                reason = ", ".join(v.confirmations or v.divergences)[:80] or "-"
        w.writerow([sk.name, static_sev, verdict, score, reason])
    if out:
        fh.close()
        console.print(f"wrote {out}")


# ---------------------------------------------------------------- skills
@app.command("skills")
def skills(
    extra: list[Path] = typer.Option(None, "--dir", "-d", help="extra skill dir(s)"),
) -> None:
    """List every skill the firewall can see on disk."""
    from firewall.skills.discover import discover_skills
    discovered = discover_skills(extra_dirs=[str(p) for p in (extra or [])])
    if not discovered:
        console.print("no skills found — looked in .claude/skills, .openclaw/skills, skills/ and ~ equivalents")
        return
    t = Table(title=f"{len(discovered)} skills found")
    t.add_column("name"); t.add_column("version"); t.add_column("path"); t.add_column("description")
    for s in discovered:
        t.add_row(s.name, s.version or "—", str(s.path), s.description[:60])
    console.print(t)


@app.command("hook")
def hook(
    agent: str = typer.Argument("generic",
        help="openclaw | hermes | claude-code | cursor | codex | gemini | opencode | generic"),
    port: int = typer.Option(8080, "--port", help="firewall proxy port"),
    host: str = typer.Option("127.0.0.1", "--host"),
) -> None:
    """Print the env vars / config to route an agent's egress through the firewall.

    Copy-paste the output into your shell, then start the agent normally.
    The per-agent instructions come from the registry in
    firewall/integrations/agents.py.
    """
    from firewall.integrations.agents import resolve
    proxy = f"http://{host}:{port}"
    profile = resolve(agent)
    typer.echo("\n".join(profile.hook_lines(proxy)))


@app.command("agents")
def agents_cmd() -> None:
    """List every agent framework the firewall knows how to adapt to."""
    from firewall.integrations.agents import all_profiles
    t = Table(title="adaptable agents")
    t.add_column("agent"); t.add_column("runtime"); t.add_column("egress")
    t.add_column("skill dirs")
    for p in all_profiles():
        dirs = ", ".join(p.project_dirs + tuple(f"~/{d}" for d in p.home_dirs)) or "—"
        t.add_row(p.display, p.runtime or "—", p.egress, dirs)
    console.print(t)


@app.command("integrations")
def integrations(
    what: str = typer.Argument(..., help="openclaw-bootstrap | list"),
) -> None:
    """Print absolute paths to integration helpers shipped with the package.

    Examples:
      firewall integrations openclaw-bootstrap   # path to proxy-bootstrap.js
      firewall integrations list                 # list everything that ships
    """
    pkg = Path(__file__).parent
    bootstrap = pkg / "integrations" / "openclaw" / "proxy-bootstrap.js"
    if what in {"openclaw-bootstrap", "openclaw", "bootstrap"}:
        if not bootstrap.exists():
            console.print(f"[red]not found: {bootstrap}[/red]")
            raise typer.Exit(2)
        # Shell-friendly: no Rich wrapping; usable in $(...) substitution.
        typer.echo(str(bootstrap))
        return
    if what == "list":
        t = Table(title="firewall integrations")
        t.add_column("name"); t.add_column("path")
        t.add_row("openclaw-bootstrap", str(bootstrap))
        console.print(t)
        return
    console.print(f"[red]unknown integration: {what}[/red]")
    raise typer.Exit(2)


@app.command("doctor")
def doctor() -> None:
    """Health check: config valid, API key set, ports free, optional tools.

    Exit status 0 if everything OK; 1 if any check failed.
    """
    import shutil
    import socket
    from rich.text import Text

    checks: list[tuple[str, bool, str]] = []

    cfg_path = config_path()
    if cfg_path.exists():
        try:
            cfg = load_config(cfg_path)
            checks.append(("config file parses", True, str(cfg_path)))
        except Exception as e:
            cfg = None
            checks.append(("config file parses", False, f"{cfg_path}: {e}"))
    else:
        cfg = None
        checks.append(("config file present", False,
                       f"missing — run: firewall config init"))

    if cfg is not None:
        env_name = cfg.driver.api_key_env
        has_key = bool(os.environ.get(env_name))
        checks.append((f"${env_name} set", has_key,
                       "found" if has_key else f"export {env_name}=..."))

    def _port_free(host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) != 0

    # Port checks are informational: a bound port often just means the
    # firewall is already running. Marked "(optional)" so doctor exits 0.
    for label, port in [("proxy port 8080 (optional)", 8080),
                        ("canary port 8088 (optional)", 8088)]:
        free = _port_free("127.0.0.1", port)
        checks.append((label, free,
                       "free" if free else "already bound (firewall may already be running)"))

    docker = shutil.which("docker") is not None
    checks.append(("docker (optional, for --mode docker)", docker,
                   "found" if docker else "not installed"))

    tectonic = shutil.which("tectonic") is not None
    checks.append(("tectonic (optional, for code.pdf rebuilds)", tectonic,
                   "found" if tectonic else "not installed"))

    required_failures = 0
    t = Table(title=f"firewall doctor — {len(checks)} checks", show_lines=False)
    t.add_column("check"); t.add_column("status"); t.add_column("detail", overflow="fold")
    for label, ok, detail in checks:
        sym = Text("✓", style="green") if ok else Text("✗", style="red")
        t.add_row(label, sym, detail)
        if not ok and "(optional)" not in label:
            required_failures += 1
    console.print(t)

    if required_failures:
        console.print(f"[red]{required_failures} required check(s) failed[/red]")
        raise typer.Exit(code=1)
    console.print("[green]all required checks passed[/green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
