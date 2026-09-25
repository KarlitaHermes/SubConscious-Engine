"""Build injection prompts for idle and wake events."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.checks.decisions import get_pending_decisions

_MUSIC_SCRIPT = "/home/karla/projects/karla-music/scripts/start-music-pipeline.sh"
_ACK = "ack-engine.sh with the engine-ack footer key"


def _recent_history_section(
    recent_deliveries: Optional[list[tuple[str, float]]] = None,
) -> str:
    """Build a 'Recent Activity' section for prompt context enrichment."""
    if not recent_deliveries:
        return ""
    lines = ["Recent nudges sent:"]
    for event_type, minutes_ago in recent_deliveries:
        if minutes_ago < 1:
            ago = "just now"
        elif minutes_ago < 60:
            ago = f"{int(minutes_ago)}m ago"
        else:
            ago = f"{minutes_ago / 60:.1f}h ago"
        lines.append(f"  - {event_type} ({ago})")
    return "\n".join(lines) + "\n\n"


def build_maintenance_prompt(
    vault_root: Path,
    threshold_minutes: int,
    recent_deliveries: Optional[list[tuple[str, float]]] = None,
    *,
    task_id: Optional[str] = None,
) -> str:
    """Build a maintenance nudge for Karla.

    When *task_id* is set (SE-scheduled duty, e.g. ``music_curation``), the
    prompt names that task and forbids picking a different maintenance item.
    Untagged nudges keep the free pick-one-due-task behaviour.

    Never end with a JSON schema — cheap models treat that as the final answer
    and skip tools. Match weather: name concrete actions/paths.
    """
    task_list = vault_root / "Projects" / "Maintenance" / "tasks.md"
    report_dir = vault_root / "Projects" / "Maintenance" / "Reports"
    history = _recent_history_section(recent_deliveries)
    scheduled = (str(task_id).strip() if task_id else "") or None

    if scheduled == "music_curation":
        return (
            f"[SUBCONSCIOUS] System idle detected (no human activity for {threshold_minutes}+ minutes).\n\n"
            f"{history}"
            f"SE scheduled task: music_curation\n"
            f"This is NOT a free pick. Do not run disk/hygiene/other maintenance.\n\n"
            f"Worker:\n"
            f"1. Ack in_progress ({_ACK}).\n"
            f"2. If a live Karla Music board/monitor is already running: drop "
            f"`kanban-report-music-YYYY-MM-DD-face.md` via "
            f"`~/.hermes/profiles/karla-worker/bin/write-inbox-report.sh` "
            f"(reason `already running`), then ack done. Never raw cat / vault_write to Inbox.\n"
            f"3. Otherwise start `{_MUSIC_SCRIPT}` in background (terminal). "
            f"Script monitor owns success/block Inbox `-face` report.\n"
            f"4. If start fails: same writer → `…-face.md` with the failure, ack done.\n"
            f"5. Do not stop at a plan. Use tools before any summary.\n"
        )

    if scheduled:
        return (
            f"[SUBCONSCIOUS] System idle detected (no human activity for {threshold_minutes}+ minutes).\n\n"
            f"{history}"
            f"SE scheduled task: {scheduled}\n"
            f"This nudge is NOT a free pick. Execute task_id=\"{scheduled}\" only.\n\n"
            f"Task file: {task_list}\n"
            f"Reports directory: {report_dir}\n\n"
            f"Worker:\n"
            f"1. Ack in_progress ({_ACK}).\n"
            f"2. Look up task_id=\"{scheduled}\" in SOUL / the task file and EXECUTE it "
            f"now with tools (script, terminal, vault_write). Do not stop at a plan.\n"
            f"3. Do NOT substitute a different maintenance item.\n"
            f"4. On skip/failure: pipe body to "
            f"`~/.hermes/profiles/karla-worker/bin/write-inbox-report.sh` "
            f"`kanban-report-…-face.md` (never raw cat / vault_write to Inbox), then ack done.\n"
            f"5. On success (or successful board start): ack done.\n"
        )

    return (
        f"[SUBCONSCIOUS] System idle detected (no human activity for {threshold_minutes}+ minutes).\n\n"
        f"{history}"
        f"Task file: {task_list}\n"
        f"Reports directory: {report_dir}\n\n"
        f"Worker:\n"
        f"1. Ack in_progress ({_ACK}).\n"
        f"2. Read the task file with tools. Pick ONE task that is DUE "
        f"(Last done / cooldown elapsed).\n"
        f"3. EXECUTE that task with tools now (script, terminal, vault_write). "
        f"Update Last done and WRITE a report under {report_dir}. "
        f"If Face must know: "
        f"`printf '…' | ~/.hermes/profiles/karla-worker/bin/write-inbox-report.sh …-face.md` "
        f"(never raw cat / vault_write into COMMS/Inbox).\n"
        f"4. If nothing is due: WRITE a short 'All tasks up to date' report under "
        f"{report_dir}, ack done. **I10:** before any weather success/verbatim claim, run "
        f"`python3 ~/.hermes/contracts/inbox/audit-weather-drops.py --hours 48 --also-archive` "
        f"and paste only its `CLAIM:` line — never invent counts.\n"
        f"5. Do not stop at a plan or JSON. Tools first, then a one-line summary.\n"
    )


def build_research_prompt(
    vault_root: Path,
    threshold_minutes: int,
    recent_deliveries: Optional[list[tuple[str, float]]] = None,
) -> str:
    """Build a research nudge when maintenance is not the scheduled idle action."""
    task_list = vault_root / "Projects" / "Maintenance" / "web-research-tasks.md"
    report_dir = vault_root / "Projects" / "Maintenance" / "Reports"
    dream_journal = vault_root / "Projects" / "Dream-Journal"
    history = _recent_history_section(recent_deliveries)
    return (
        f"[SUBCONSCIOUS] System idle detected (no human activity for {threshold_minutes}+ minutes).\n\n"
        f"No pending maintenance this cycle — self-improvement research.\n\n"
        f"{history}"
        f"Research context:\n"
        f"- Web research topics: {task_list}\n"
        f"- DREAM suggestions: {dream_journal}\n"
        f"- Reports directory: {report_dir}\n\n"
        f"Worker:\n"
        f"1. Ack in_progress ({_ACK}).\n"
        f"2. Check {report_dir} for research in the last 48h; skip duplicates.\n"
        f"3. Pick ONE new topic from the research tasks or DREAM journal; research it "
        f"with tools; WRITE findings under {report_dir}.\n"
        f"4. If Face/Rev must know: pipe to "
        f"`~/.hermes/profiles/karla-worker/bin/write-inbox-report.sh` "
        f"`research-digest-YYYY-MM-DD-HH-face.md` "
        f"(hour 00–23; never raw cat / vault_write to Inbox).\n"
        f"5. Ack done. Do not stop at a plan or JSON — tools first.\n"
    )


def build_pending_decisions_prompt(
    vault_root: Path,
    idle_minutes: float,
    since_timestamp: float = 0.0,
    recent_deliveries: Optional[list[tuple[str, float]]] = None,
) -> str | None:
    """Build a wake-up nudge when Rev returns after an extended idle period."""
    decisions = get_pending_decisions(vault_root, since_timestamp=since_timestamp)
    if not decisions:
        return None
    decisions_text = "\n".join(decisions)
    history = _recent_history_section(recent_deliveries)
    return (
        f"[SUBCONSCIOUS] Rev has been idle for ~{int(idle_minutes)} minutes and just came back.\n\n"
        f"{history}"
        f"Pending decisions from recent reports:\n\n"
        f"{decisions_text}\n\n"
        f"Worker:\n"
        f"1. Ack in_progress ({_ACK}).\n"
        f"2. For each item, classify with tools against current project state: "
        f"(a) easy win — do it now, (b) needs Rev — prepare a one-liner, "
        f"(c) already handled — mark done.\n"
        f"3. Execute easy wins; WRITE Inbox …-face.md for anything Rev must see.\n"
        f"4. Ack done. Tools first — do not stop at a plan or JSON.\n"
    )
