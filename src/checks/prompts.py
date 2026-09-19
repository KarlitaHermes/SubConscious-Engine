"""Build injection prompts for idle and wake events."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.checks.decisions import get_pending_decisions


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
    """
    task_list = vault_root / "Projects" / "Maintenance" / "tasks.md"
    report_dir = vault_root / "Projects" / "Maintenance" / "Reports"
    history = _recent_history_section(recent_deliveries)
    scheduled = (str(task_id).strip() if task_id else "") or None

    if scheduled:
        return (
            f"[SUBCONSCIOUS] System idle detected (no human activity for {threshold_minutes}+ minutes).\n\n"
            f"{history}"
            f"SE scheduled task: {scheduled}\n"
            f"This nudge is NOT a free pick from the task list. Execute task_id=\"{scheduled}\" only.\n\n"
            f"Task file (procedure / Last done): {task_list}\n"
            f"Reports directory: {report_dir}\n\n"
            f"Karla-Worker:\n"
            f"1. Ack in_progress using the engine-ack footer key.\n"
            f"2. Look up task_id=\"{scheduled}\" in SOUL / skills / the task file and "
            f"EXECUTE it now with tools (start the board/script or run the duty). "
            f"Do not stop at a JSON plan.\n"
            f"3. Do NOT substitute a different maintenance item "
            f"(disk, hygiene, research, etc.).\n"
            f"4. On skip (already running) or failure, write an Inbox "
            f"kanban-report-…-face.md with the reason, then ack done.\n"
            f"5. On success start (board/script owns the rest), ack done.\n\n"
            f"Actions: [execute_task, skip, defer]\n"
            f"Respond with: "
            f"{{\"action\": \"...\", \"task_id\": \"{scheduled}\", \"reason\": \"...\"}}"
        )

    return (
        f"[SUBCONSCIOUS] System idle detected (no human activity for {threshold_minutes}+ minutes).\n\n"
        f"{history}"
        f"Task file: {task_list}\n"
        f"Reports directory: {report_dir}\n\n"
        f"Karla: spawn a sub-agent with this instruction:\n\n"
        f"Read the maintenance tasks file. Check the 'Last done' timestamp and cooldown "
        f"for each task. Pick ONE task that is DUE (cooldown has passed). If NO tasks "
        f"are due, write a report saying 'All tasks up to date' and exit. "
        f"If a task is due, EXECUTE it with tools (do not stop at a JSON plan), write a "
        f"report to the reports directory, and update the 'Last done' timestamp in the "
        f"task file.\n\n"
        f"Actions: [execute_task, skip_all, defer]\n"
        f"Respond with: {{\"action\": \"...\", \"task_id\": \"...\", \"reason\": \"...\"}}"
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
        f"No pending maintenance tasks scheduled this cycle. Time for self-improvement research.\n\n"
        f"{history}"
        f"Research context:\n"
        f"- Web research topics: {task_list}\n"
        f"- DREAM suggestions: {dream_journal}\n"
        f"- Reports directory (check existing reports first): {report_dir}\n\n"
        f"Karla: spawn a sub-agent with this instruction:\n\n"
        f"Check the reports directory for recent research (last 48h). If a research topic "
        f"was already covered recently, skip it. Pick ONE new topic from the web research "
        f"tasks file or DREAM journal. Research it thoroughly and write findings to the "
        f"reports directory. Only flag something for Rev if it's genuinely interesting or urgent.\n\n"
        f"Actions: [research_topic, skip_all, flag_for_rev]\n"
        f"Respond with: {{\"action\": \"...\", \"topic\": \"...\", \"reason\": \"...\"}}"
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
        f"There are pending decisions from recent reports:\n\n"
        f"{decisions_text}\n\n"
        f"Karla: spawn a sub-agent to evaluate these items. Have it check each one against "
        f"the current project state and classify as: (a) easy win — do it now, "
        f"(b) needs Rev's input — prepare a one-liner summary for Rev, "
        f"(c) already handled or not actionable — mark done. "
        f"You just review the sub-agent's classification and act accordingly.\n\n"
        f"Actions: [execute_now, ask_rev, mark_done]\n"
        f"Respond with: {{\"action\": \"...\", \"item\": \"...\", \"reason\": \"...\"}}"
    )
