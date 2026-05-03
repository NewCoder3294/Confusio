"""Offline integration smoke for the orchestrator.

Drives a 4-persona campaign through the full state machine with a stubbed
LLM and stubbed Telethon. No network. No real OpenAI / Telegram calls.

Asserts the PRD acceptance criteria that don't need live creds:
  AC-2 seed appears in queue after submission
  AC-3 approve causes a posted record with telegram_message_id
  AC-4 jittered non-seed posts queue with previous_posts context
  AC-5 reject is recorded
  AC-6 edit-and-approve preserves original
  AC-7 daemon restart preserves campaign state (we re-init Storage and rerun)
  AC-8 posting failure recorded as failed, daemon does not crash
  AC-9/10 pause/abort transitions
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import time
from pathlib import Path

# Use a scratch DB / log so we don't pollute the real ones.
SCRATCH = Path(__file__).parent / "social" / ".qa_scratch"
SCRATCH.mkdir(exist_ok=True)
os.environ["MENDACITY_LOG_LEVEL"] = "WARNING"

from social import storage as storage_mod  # noqa: E402

storage_mod.DB_PATH = SCRATCH / "qa.db"
storage_mod.LOG_PATH = SCRATCH / "qa.jsonl"

from social.orchestrator import Orchestrator  # noqa: E402
from social.persona_agent import PersonaAgent  # noqa: E402
from social.personas import load_personas  # noqa: E402
from social.storage import Campaign, GeneratedPost, Storage  # noqa: E402
from social.telegram_client import (  # noqa: E402
    PostResult,
    SessionExpiredError,
    TelegramError,
)


# ---------- stubs ----------

class StubLLM:
    def __init__(self):
        self.calls = []

    async def generate(self, prompt, *, model=None, temperature=0.85, max_tokens=400):
        self.calls.append(prompt)
        # Echo the role/persona implied by the prompt for inspectability.
        first_line = prompt.splitlines()[0]
        return f"[stub] {first_line} (call#{len(self.calls)})"


class StubTG:
    def __init__(self, *, fail_on_send: bool = False):
        self.sent: list[tuple[str, str]] = []
        self.joined: list[str] = []
        self.fail_on_send = fail_on_send

    async def start(self):
        pass

    async def stop(self):
        pass

    async def join_channel(self, channel):
        self.joined.append(channel)

    async def send_message(self, channel, text):
        self.sent.append((channel, text))
        if self.fail_on_send:
            raise TelegramError("simulated TG failure")
        from datetime import datetime, timezone

        return PostResult(
            telegram_message_id=10000 + len(self.sent),
            posted_at=datetime.now(timezone.utc).isoformat(),
        )


async def _build_orch(*, fail_send_for: set[str] | None = None) -> tuple[Orchestrator, dict, dict]:
    fail_send_for = fail_send_for or set()
    personas = load_personas(require_sessions=False)
    llm = StubLLM()
    tgs: dict[str, StubTG] = {}
    agents: dict[str, PersonaAgent] = {}
    for pid, persona in personas.items():
        tgs[pid] = StubTG(fail_on_send=(pid in fail_send_for))
        agents[pid] = PersonaAgent(persona, llm, tgs[pid])
    storage = Storage(db_path=storage_mod.DB_PATH, log_path=storage_mod.LOG_PATH)
    await storage.init()
    orch = Orchestrator(
        agents, storage, allowed_channels=["@mendacity_demo_channel"]
    )
    return orch, tgs, {"llm": llm, "personas": personas}


# ---------- helpers ----------

def expect(cond, msg):
    if not cond:
        print(f"  FAIL: {msg}")
        global failures
        failures += 1
    else:
        print(f"  ok:   {msg}")


def reset_db():
    if storage_mod.DB_PATH.exists():
        storage_mod.DB_PATH.unlink()
    if storage_mod.LOG_PATH.exists():
        storage_mod.LOG_PATH.unlink()


failures = 0


# ---------- tests ----------

async def test_seed_then_jitter_then_approve_chain():
    print("\n[T1] full campaign: seed → approve → posted → schedule → witnesses")
    orch, tgs, ctx = await _build_orch()

    c = Campaign.new(
        intent="unusual movement near M-04 highway around dawn",
        channel="@mendacity_demo_channel",
        delay_range_seconds=(0, 1),  # near-zero so the schedule fires immediately
        created_by="qa",
        roster={
            "anton_kh": "seed",
            "olga_kyiv": "witness",
            "dmitry_dn": "reaction",
            "news_aggregator": "aggregator",
        },
    )
    await orch.submit_campaign(c)
    # Tick 1: should generate seed (pending_approval)
    await orch._tick()
    pending = await orch.storage.list_pending()
    expect(len(pending) == 1, "after tick 1, exactly 1 pending (seed)")
    expect(pending[0].role == "seed", "pending post is the seed")
    expect(pending[0].persona_id == "anton_kh", "seed persona is anton_kh")

    # Approve seed
    await orch.approve(pending[0].id)
    # Tick 2: should post the seed → telegram, then schedule witnesses, then maybe generate due
    await orch._tick()
    posted = await orch.storage.list_posts_for_campaign(c.id, statuses=("posted",))
    expect(len(posted) == 1, "seed is posted after approval+tick")
    expect(
        posted[0].telegram_message_id is not None, "seed has telegram_message_id"
    )
    expect(
        len(tgs["anton_kh"].sent) == 1, "anton_kh's TG client sent exactly one message"
    )

    # Wait briefly so any scheduled-at within 0-1s is due, then tick again to generate witnesses
    await asyncio.sleep(1.2)
    await orch._tick()
    pending2 = await orch.storage.list_pending()
    expect(
        len(pending2) >= 1,
        f"non-seed posts queued after delay (got {len(pending2)})",
    )
    roles_in_queue = {p.role for p in pending2}
    expect(
        roles_in_queue.issubset({"witness", "reaction", "aggregator"}),
        f"queued roles are non-seed: {roles_in_queue}",
    )

    # Approve them all and let the loop post
    for p in pending2:
        await orch.approve(p.id)
    await orch._tick()
    posted_total = await orch.storage.list_posts_for_campaign(
        c.id, statuses=("posted",)
    )
    expect(
        len(posted_total) == 1 + len(pending2),
        f"all approved posts now posted (got {len(posted_total)})",
    )

    # AC-4: previous_posts context — re-derive what we'd hand to the next agent
    prev = await orch._previous_posts(c.id)
    expect(
        len(prev) == len(posted_total),
        "previous_posts list matches posted count",
    )
    expect(prev[0].posted_at_offset == "T+0m", "first prev post offset is T+0m")
    if len(prev) > 1:
        expect(
            prev[-1].posted_at_offset.startswith("T+"),
            f"later prev post has T+ offset (got {prev[-1].posted_at_offset})",
        )


async def test_edit_and_approve_preserves_original():
    print("\n[T2] edit-and-approve preserves both original and edited content")
    reset_db()
    orch, tgs, _ = await _build_orch()
    c = Campaign.new(
        intent="x", channel="@mendacity_demo_channel",
        delay_range_seconds=(0, 1), created_by="qa",
        roster={"anton_kh": "seed"},
    )
    await orch.submit_campaign(c)
    await orch._tick()
    [post] = await orch.storage.list_pending()
    original = post.generated_content
    await orch.approve(post.id, edited_content="OPERATOR EDIT")
    refreshed = await orch.storage.get_post(post.id)
    expect(refreshed.generated_content == original, "original preserved")
    expect(refreshed.edited_content == "OPERATOR EDIT", "edited stored")
    expect(refreshed.final_content == "OPERATOR EDIT", "final_content uses edit")
    await orch._tick()
    expect(
        tgs["anton_kh"].sent[-1][1] == "OPERATOR EDIT",
        "edited content is what reached TG",
    )


async def test_reject_without_regenerate_does_not_resend():
    print("\n[T3] FR-5.5 reject (no regen) stalls the campaign — no auto-regen")
    reset_db()
    orch, tgs, _ = await _build_orch()
    c = Campaign.new(
        intent="x", channel="@mendacity_demo_channel",
        delay_range_seconds=(0, 1), created_by="qa",
        roster={"anton_kh": "seed"},
    )
    await orch.submit_campaign(c)
    await orch._tick()
    [post] = await orch.storage.list_pending()
    await orch.reject(post.id, regenerate=False)
    await orch._tick()
    pending = await orch.storage.list_pending()
    posted = await orch.storage.list_posts_for_campaign(c.id, statuses=("posted",))
    expect(len(tgs["anton_kh"].sent) == 0, "no TG send after pure reject")
    expect(len(pending) == 0, f"queue empty after pure reject (got {len(pending)})")
    expect(len(posted) == 0, "no posted after pure reject")


async def test_reject_with_regenerate_creates_new_pending():
    print("\n[T3b] FR-5.5 reject+regen on non-seed actually triggers regeneration")
    reset_db()
    orch, tgs, _ = await _build_orch()
    c = Campaign.new(
        intent="x", channel="@mendacity_demo_channel",
        delay_range_seconds=(0, 1), created_by="qa",
        roster={"anton_kh": "seed", "olga_kyiv": "witness"},
    )
    await orch.submit_campaign(c)
    # Drive to seed-posted, schedule witnesses, generate witness pending
    await orch._tick()
    [seed] = await orch.storage.list_pending()
    await orch.approve(seed.id)
    await orch._tick()
    await asyncio.sleep(1.2)
    await orch._tick()
    pending = await orch.storage.list_pending()
    witness = next((p for p in pending if p.role == "witness"), None)
    expect(witness is not None, "witness post pending")

    # Now reject with regenerate=True
    await orch.reject(witness.id, regenerate=True)
    pending_after_reject = await orch.storage.list_pending()
    expect(
        len(pending_after_reject) == 0,
        "rejected witness immediately leaves the pending queue",
    )

    # Tick: schedule should be reset to generated=0; _generate_due picks it up
    await orch._tick()
    pending_after_regen = await orch.storage.list_pending()
    new_witness = next(
        (p for p in pending_after_regen if p.role == "witness" and p.id != witness.id),
        None,
    )
    expect(new_witness is not None, "regen produced a fresh witness post")


async def test_post_failure_marks_failed_and_daemon_continues():
    print("\n[T4] AC-8 posting failure → status=failed, daemon does not crash")
    reset_db()
    orch, tgs, _ = await _build_orch(fail_send_for={"anton_kh"})
    c = Campaign.new(
        intent="x", channel="@mendacity_demo_channel",
        delay_range_seconds=(0, 1), created_by="qa",
        roster={"anton_kh": "seed"},
    )
    await orch.submit_campaign(c)
    await orch._tick()
    [post] = await orch.storage.list_pending()
    await orch.approve(post.id)
    await orch._tick()  # this should attempt to send and fail
    refreshed = await orch.storage.get_post(post.id)
    expect(refreshed.status == "failed", f"status=failed (got {refreshed.status})")
    expect(refreshed.error is not None, "error string recorded")
    # Subsequent ticks must not crash on a campaign with failed seed
    await orch._tick()
    await orch._tick()


async def test_pause_resume_abort():
    print("\n[T5] AC-9/10 pause/resume/abort transitions")
    reset_db()
    orch, _, _ = await _build_orch()
    c = Campaign.new(
        intent="x", channel="@mendacity_demo_channel",
        delay_range_seconds=(0, 1), created_by="qa",
        roster={"anton_kh": "seed", "olga_kyiv": "witness"},
    )
    await orch.submit_campaign(c)
    await orch._tick()  # generate seed
    await orch.pause(c.id)
    refreshed = await orch.storage.get_campaign(c.id)
    expect(refreshed.status == "paused", "paused status set")
    await orch._tick()  # paused: no further generation
    pending_before = len(await orch.storage.list_pending())
    await orch._tick()
    expect(len(await orch.storage.list_pending()) == pending_before, "no new gen while paused")
    await orch.resume(c.id)
    refreshed = await orch.storage.get_campaign(c.id)
    expect(refreshed.status == "running", "resumed status")
    await orch.abort(c.id)
    refreshed = await orch.storage.get_campaign(c.id)
    expect(refreshed.status == "aborted", "aborted status")
    pending_after = await orch.storage.list_pending()
    expect(
        all(p.campaign_id != c.id for p in pending_after),
        "aborted campaign's pending posts are removed from queue",
    )


async def test_validation_rules():
    print("\n[T6] campaign validation: channel allow-list, single seed, known personas")
    reset_db()
    orch, _, _ = await _build_orch()
    from social.orchestrator import CampaignValidationError

    # Bad channel
    c = Campaign.new(intent="x", channel="@bad", delay_range_seconds=(0, 1),
                     created_by="qa", roster={"anton_kh": "seed"})
    try:
        await orch.submit_campaign(c)
        expect(False, "should reject unknown channel")
    except CampaignValidationError:
        expect(True, "unknown channel rejected")

    # Multiple seeds
    c = Campaign.new(intent="x", channel="@mendacity_demo_channel",
                     delay_range_seconds=(0, 1), created_by="qa",
                     roster={"anton_kh": "seed", "olga_kyiv": "seed"})
    try:
        await orch.submit_campaign(c)
        expect(False, "should reject multiple seeds")
    except CampaignValidationError:
        expect(True, "multiple seeds rejected")

    # Unknown persona
    c = Campaign.new(intent="x", channel="@mendacity_demo_channel",
                     delay_range_seconds=(0, 1), created_by="qa",
                     roster={"ghost": "seed"})
    try:
        await orch.submit_campaign(c)
        expect(False, "should reject unknown persona")
    except CampaignValidationError:
        expect(True, "unknown persona rejected")


async def test_restart_preserves_state():
    print("\n[T7] AC-7 restart: a fresh Storage sees prior campaigns and pending posts")
    reset_db()
    orch1, _, _ = await _build_orch()
    c = Campaign.new(intent="x", channel="@mendacity_demo_channel",
                     delay_range_seconds=(0, 1), created_by="qa",
                     roster={"anton_kh": "seed", "olga_kyiv": "witness"})
    await orch1.submit_campaign(c)
    await orch1._tick()
    pending_before = await orch1.storage.list_pending()
    expect(len(pending_before) == 1, "seed pending pre-restart")

    # "Restart": new Storage instance pointing at same DB
    orch2, _, _ = await _build_orch()
    pending_after = await orch2.storage.list_pending()
    expect(
        len(pending_after) == len(pending_before),
        "pending queue preserved across restart",
    )
    campaign = await orch2.storage.get_campaign(c.id)
    expect(campaign is not None and campaign.status == "running",
           "campaign status preserved")


async def test_audit_log_has_required_fields():
    print("\n[T8] audit log entries carry the PRD §6.7 fields")
    reset_db()
    orch, _, _ = await _build_orch()
    c = Campaign.new(intent="x", channel="@mendacity_demo_channel",
                     delay_range_seconds=(0, 1), created_by="qa",
                     roster={"anton_kh": "seed"})
    await orch.submit_campaign(c)
    await orch._tick()
    [post] = await orch.storage.list_pending()
    await orch.approve(post.id)
    await orch._tick()

    log = orch.storage.tail_log(50)
    events = {e["event"] for e in log}
    expect(
        {"campaign_created", "generation_requested", "content_generated",
         "post_approved", "post_sent"}.issubset(events),
        f"all expected events present (got {events})",
    )
    # Approval entry must carry content + content_hash + operator
    approve_entries = [e for e in log if e["event"] == "post_approved"]
    expect(len(approve_entries) == 1, "exactly one approve entry")
    a = approve_entries[0]
    expect("ts" in a and "campaign_id" in a and "persona_id" in a, "core ids present")
    expect("content_hash" in a and a["content_hash"].startswith("sha256:"),
           "sha256 content_hash present on approval")
    expect(a["operator"] == "unknown" or a["operator"], "operator recorded")


async def test_streamlit_app_imports_under_streamlit_runner():
    print("\n[T9] streamlit-runtime sanity: app.py loads without exception")
    import subprocess
    # Use streamlit's `--help` is not enough; probe by importing inside a child.
    proc = subprocess.run(
        [sys.executable, "-c",
         "import os; os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS']='false'; "
         "from streamlit.testing.v1 import AppTest; "
         "at = AppTest.from_file('social/app.py'); at.run(timeout=15); "
         "print('streamlit-OK exceptions=', len(at.exception)); "
         "[print('  exc:', e.value) for e in at.exception]"],
        capture_output=True, text=True, timeout=60,
    )
    print("  stdout:", proc.stdout.strip())
    if proc.returncode != 0:
        print("  stderr:", proc.stderr.strip()[-500:])
    expect(proc.returncode == 0, "streamlit AppTest exits 0")
    expect("streamlit-OK exceptions= 0" in proc.stdout,
           "no exceptions raised during Streamlit run")


async def main():
    await test_seed_then_jitter_then_approve_chain()
    await test_edit_and_approve_preserves_original()
    await test_reject_without_regenerate_does_not_resend()
    await test_reject_with_regenerate_creates_new_pending()
    await test_post_failure_marks_failed_and_daemon_continues()
    await test_pause_resume_abort()
    await test_validation_rules()
    await test_restart_preserves_state()
    await test_audit_log_has_required_fields()
    await test_streamlit_app_imports_under_streamlit_runner()


if __name__ == "__main__":
    asyncio.run(main())
    if failures:
        print(f"\n=== {failures} FAILURES ===")
        sys.exit(1)
    print("\n=== ALL PASSED ===")
    shutil.rmtree(SCRATCH, ignore_errors=True)
