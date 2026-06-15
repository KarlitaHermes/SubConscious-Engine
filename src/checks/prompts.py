"""Build injection prompts for idle and wake events."""

from __future__ import annotations

from pathlib import Path

from src.checks.decisions import get_pending_decisions


def build_maintenance_prompt(vault_root: Path, threshold_minutes: int) -> str:
    """Build a maintenance nudge for Karla."""
    task_list = vault_root / "Projects" / "ORCHESTRATOR" / "Tasks" / "maintenance-tasks.md"
    report_dir = vault_root / "Projects" / "ORCHESTRATOR" / "Reports"
    return (
        f"[SUBCONSCIOUS] System idle detected (no human activity for {threshold_minutes}+ minutes).\n\n"
        f"Task file: {task_list}\n"
        f"Reports directory: {report_dir}\n\n"
        f"Karla: spawn a sub-agent with this instruction:\n\n"
        f"Read the maintenance tasks file. Check the 'Last done' timestamp and cooldown "
        f"for each task. Pick ONE task that is DUE (cooldown has passed). If NO tasks "
        f"are due, write a report saying 'All tasks up to date' and exit. "
        f"If a task is due, execute it, write a report to the reports directory, "
        f"and update the 'Last done' timestamp in the task file."
    )


def build_research_prompt(vault_root: Path, threshold_minutes: int) -> str:
    """Build a research nudge when maintenance is not the scheduled idle action."""
    task_list = vault_root / "Projects" / "ORCHESTRATOR" / "Tasks" / "web-research-tasks.md"
    report_dir = vault_root / "Projects" / "ORCHESTRATOR" / "Reports"
    dream_journal = vault_root / "Projects" / "Dream-Journal"
    return (
        f"[SUBCONSCIOUS] System idle detected (no human activity for {threshold_minutes}+ minutes).\n\n"
        f"No pending maintenance tasks scheduled this cycle. Time for self-improvement research.\n\n"
        f"Research context:\n"
        f"- Web research topics: {task_list}\n"
        f"- DREAM suggestions: {dream_journal}\n"
        f"- Reports directory (check existing reports first): {report_dir}\n\n"
        f"Karla: spawn a sub-agent with this instruction:\n\n"
        f"Check the reports directory for recent research (last 48h). If a research topic "
        f"was already covered recently, skip it. Pick ONE new topic from the web research "
        f"tasks file or DREAM journal. Research it thoroughly and write findings to the "
        f"reports directory. Only flag something for Rev if it's genuinely interesting or urgent."
    )


def build_pending_decisions_prompt(
    vault_root: Path,
    idle_minutes: float,
    since_timestamp: float = 0.0,
) -> str | None:
    """Build a wake-up nudge when Rev returns after an extended idle period."""
    decisions = get_pending_decisions(vault_root, since_timestamp=since_timestamp)
    if not decisions:
        return None
    decisions_text = "\n".join(decisions)
    return (
        f"[SUBCONSCIOUS] Rev has been idle for ~{int(idle_minutes)} minutes and just came back.\n\n"
        f"There are pending decisions from recent reports:\n\n"
        f"{decisions_text}\n\n"
        f"Karla: spawn a sub-agent to evaluate these items. Have it check each one against "
        f"the current project state and classify as: (a) easy win — do it now, "
        f"(b) needs Rev's input — prepare a one-liner summary for Rev, "
        f"(c) already handled or not actionable — mark done. "
        f"You just review the sub-agent's classification and act accordingly."
    )
