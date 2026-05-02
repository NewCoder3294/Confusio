# `social/` — Mendacity AI Telegram Agent

Implementation of issue #3. A multi-persona LLM agent system that produces
coordinated, role-differentiated content on Telegram with mandatory
operator-in-the-loop approval.

See the PRD in the issue thread for full requirements. This README is the
operational runbook.

## Architecture

Two long-running processes share a sqlite DB and an append-only log:

```
┌────────────────────────┐         ┌────────────────────────────┐
│  Streamlit (app.py)    │  reads  │  Orchestrator daemon       │
│  - operator console    │ ◄──────►│  (orchestrator.py)         │
│  - writes intent only  │ sqlite  │  - generates via LLM       │
└────────────────────────┘  + log  │  - posts via Telethon      │
                                   │  - schedules jittered runs │
                                   └────────────────────────────┘
                                                │
                                       Telethon │  OpenAI
                                                ▼     │
                                         ┌──────────────┐
                                         │  4 persona   │
                                         │  TG sessions │
                                         └──────────────┘
```

The Streamlit UI never touches Telethon. All Telegram I/O is the daemon's
responsibility, which keeps session locks and the audit trail in one place.

## File map

| File | Role |
| --- | --- |
| `personas/*.json` | Author-curated persona profiles |
| `personas.py` | Pydantic loader (fail-fast on missing fields/sessions) |
| `prompts.py` | Role templates: seed / witness / reaction / aggregator |
| `llm.py` | AsyncOpenAI wrapper with one-retry on transient errors |
| `telegram_client.py` | Per-persona Telethon client + FloodWait backoff |
| `storage.py` | aiosqlite schema + append-only `posts.jsonl` |
| `persona_agent.py` | Binds one persona to its LLM and TG client |
| `orchestrator.py` | Campaign lifecycle, scheduling, approval routing |
| `app.py` | Streamlit operator console |
| `scripts/login_persona.py` | One-time interactive Telethon login |
| `config/api_credentials.env` | Secrets (gitignored) |
| `config/channel_config.json` | Channel allow-list |

## First-time setup

### 1. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Fill in credentials

Edit `social/config/api_credentials.env`:

```
OPENAI_API_KEY=sk-...        # rotate after any leak before pasting
TELEGRAM_API_ID=...          # from https://my.telegram.org/apps
TELEGRAM_API_HASH=...
OPERATOR_USER_ID=nick        # recorded on every approval action
```

This file is gitignored — never commit it.

### 3. Create the demo channel and add the personas

In your personal Telegram app:

1. Create a public channel and remember its handle (e.g. `@mendacity_demo_channel`).
2. Add the channel handle to `social/config/channel_config.json` — the
   orchestrator rejects campaigns targeting any channel not on the allow-list.
3. After step 4 below, log into each persona on a phone or web client and
   join the channel. The orchestrator will also call `JoinChannelRequest`
   on first post, but having the personas pre-joined avoids edge cases for
   private channels.

### 4. Log in each persona

Each persona needs its own real Telegram account (BotFather bots will not
work — they expose a visible bot badge). For each `<persona_id>`:

```bash
.venv/bin/python -m social.scripts.login_persona anton_kh
# enter the phone number, then the SMS code, then 2FA password if set
```

Repeat for `olga_kyiv`, `dmitry_dn`, `news_aggregator`. After this you'll
have four files under `social/sessions/`.

## Running a campaign

Open two terminals.

**Terminal 1 — orchestrator daemon:**

```bash
.venv/bin/python -m social.orchestrator
```

Logs to stderr. The daemon performs all Telegram I/O.

**Terminal 2 — operator console:**

```bash
.venv/bin/streamlit run social/app.py
```

The UI opens on http://localhost:8501.

### Operator workflow

1. **Section A** — write an intent, pick the channel, assign roles
   (exactly one `seed`, others `witness`/`reaction`/`aggregator`),
   set the delay range, click *Start campaign*.
2. **Section B** — within ~10s the seed post appears. Approve, edit-and-approve,
   or reject. On approval the daemon posts to Telegram.
3. After the seed lands, witness/reaction/aggregator posts arrive in the
   queue with random jitter inside your delay range. Approve each.
4. **Section C** — watch sent posts and the audit log feed.

`Ctrl-C` the daemon to pause. Restart it and active campaigns resume from
the DB.

## Operational invariants

- **No autonomous posting.** The daemon only posts entries with status
  `approved`. Streamlit is the only writer of that status.
- **Channel allow-list.** `submit_campaign` rejects unknown channels.
- **Audit trail is append-only.** `posts.jsonl` is never rewritten.
- **Secrets stay local.** `sessions/`, `posts.jsonl`, `mendacity.db`, and
  `api_credentials.env` are all gitignored.

## Troubleshooting

- *`SessionExpiredError`*: re-run `login_persona.py` for that persona.
- *`RateLimitedError`*: Telethon hit FloodWait. The daemon retries with
  exponential backoff up to 3 attempts, then surfaces the post as `failed`.
- *`channel ... not in allow-list`*: edit `channel_config.json`.
- *`OPENAI_API_KEY not set`*: fill in `api_credentials.env`. The error
  surfaces at first generation, not at startup.
