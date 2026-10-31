# LarpFlow

> **Autonomous developer log generator and multi-platform social syndication engine.**  
> Turn your actual GitHub code, commits, and diffs into authentic, factual dev-logs across X, LinkedIn, Reddit, Discord, Facebook, and GitHub READMEs — with zero AI-slop and human approval.

---

## ⚡ What is LarpFlow?

LarpFlow inspects your real GitHub repositories (commits, diffs, closed issues, file trees, and READMEs), pairs them with your problem/solution notes or auto-infers context from recent commits, and drafts tailored updates for every developer platform.

**Nothing is posted until you approve it.**

```
       CLI / Antigravity Agent / Telegram
                       │
                       ▼
 ┌───────────────────────────────────────────┐
 │            1. GitHub Ingestor             │  ──> Pulls commits, diffs, issues, README
 └───────────────────────────────────────────┘
                       │
                       ▼
 ┌───────────────────────────────────────────┐
 │          2. Narrative Stylist (LLM)       │  ──> Generates platform-specific drafts
 ├───────────────────────────────────────────┤
 │         Anti-Slop Rule Checker            │  ──> Enforces word counts, tweet lengths,
 └───────────────────────────────────────────┘      banned buzzwords, Reddit headers (3x retry)
                       │
                       ▼
 ┌───────────────────────────────────────────┐
 │              3. Gatekeeper                │  ──> Human review & approval
 └───────────────────────────────────────────┘      (Terminal CLI, Editor preview, or Telegram)
                       │
                 [ Approve ]
                       │
                       ▼
 ┌───────────────────────────────────────────┐
 │              4. Dispatcher                │  ──> X (Thread + Media) | LinkedIn (Images) |
 └───────────────────────────────────────────┘      Reddit | Discord | Facebook | GitHub
                       │
                       ▼
              storage/history.sqlite
```

---

## 🚀 Key Features

- **Local Git Ingestion (Zero-Latency & Offline):** Ingest directly from local repositories (`larpflow run .` or `/path/to/repo`). Extracts diffs, commits, and file trees in $<50\text{ms}$ with zero network requests or GitHub tokens required.
- **Selective / Targeted Drafting:** Pass `-p` / `--platforms` to generate drafts *only* for the platforms you care about (e.g. `larpflow run . -p linkedin,discord`). Cuts token usage by 60% and avoids unnecessary rule retries for skipped channels.
- **Anti-Hallucination & Anti-Slop Guardrails:** Ground truth comes strictly from your code diffs, persona, and LinkedIn profile. Banned corporate PR buzzwords (*"excited to announce"*, *"game changer"*, *"unleash"*, *"delve"*), no invented benchmark figures, and zero marketing hyperbole.
- **Multi-Platform Syndication:**
  - **X (Twitter):** 4-tweet narrative thread with local media/screenshot attachments ($\le 275$ chars/tweet).
  - **LinkedIn:** 140–350 word structured post-mortem with media uploads via LinkedIn API.
  - **Reddit:** Technical post-mortem formatted with `### The Bottleneck`, `### What Failed`, `### The Fix` (no links in body, auto-flair template matching).
  - **Discord:** Rich embed dev-log with image carousel attachments via webhooks.
  - **Facebook:** Community-friendly project showcase with clean formatting.
  - **GitHub:** Direct commit & push of Architecture & Trade-offs into repository README, plus Profile README generator.
- **Fast-Path 1-Step Execution:** Draft and publish in a single command (`--publish -p linkedin,discord --yes`).
- **Flexible Review Gate:** Review in terminal, auto-open drafts in your favorite editor as markdown, or manage via Telegram bot buttons.
- **Safe by Default:** `DRY_RUN=true` out of the box prevents accidental posting until you're ready.

---

## 📦 Installation & Setup

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/your-username/larpflow.git
cd larpflow

python3 -m venv venv
source venv/bin/activate    # Mac / Linux
# venv\Scripts\activate     # Windows

pip install -e .
```

### 2. Configure Environment (`.env`)

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Fill in your API keys in `.env`:
- **`LLM_API_KEY`**: Your Gemini or OpenAI API key.
- **`LLM_MODEL`**: e.g., `gemini-3.8-flash` or `gpt-4o-mini`.
- **`GITHUB_USER`**: Your GitHub handle (auto-detected if using `gh` CLI).
- **Platform Keys**: Add tokens for whichever platforms you want to post to (X, LinkedIn, Discord, Reddit, Facebook). Platforms without keys are cleanly skipped.

Run the diagnostic tool at any time to verify your keys:

```bash
larpflow doctor
```

### 3. Personalize Your Persona & Voice

- **`config/persona.json`**: Copy `config/persona.example.json` to `config/persona.json`. List your actual technical stack, handles, and banned phrases.
- **`config/linkedin_profile.md`**: Copy `config/linkedin_profile.example.md` to `config/linkedin_profile.md`. Paste your headline, about section, and experience so the LLM writes in your genuine voice.

---

## 🛠️ CLI Usage

### 1. Generate Drafts (Local or Remote)

**Local Git Repository (Zero Latency & Offline):**
Inspects local git history, diffs, and files instantly with zero network calls:
```bash
# Ingest current directory
larpflow run .

# Ingest any local project directory
larpflow run /path/to/my-project
# or relative path:
larpflow run ../my-project
```

**Remote GitHub Repository (Auto-Infer from Commits):**
Inspects remote repository commits and diffs via GitHub API:
```bash
larpflow run <repo_name>
```

### 2. Selective & Targeted Drafting (Faster, Lower Token Cost)

Draft only for the platforms you actually plan to publish to:
```bash
# Draft only for LinkedIn and Discord
larpflow run . -p linkedin,discord

# Draft only for X (Twitter)
larpflow run <repo_name> -p x
```

### 3. 1-Step Fast-Path (Generate & Publish)

Generates the drafts and immediately dispatches to your target platforms:

```bash
larpflow run <repo_name> --publish -p linkedin,discord --yes
```

### 3. Custom Narrative Types & Context

```bash
larpflow run <repo_name> \
  --type architecture \
  --problem "High CPU overhead when polling events on the main thread" \
  --solution "Implemented monotonic CACurrentMediaTime interpolation and event-driven cadence" \
  --image /path/to/screenshot.png
```

Supported narrative types (`-t` / `--type`):
- `auto`: Balances project scope, bottleneck, and engineering takeaways.
- `intro`: High-level, friendly showcase. Zero low-level system jargon.
- `motivation`: Personal backstory, user problem, why existing tools fell short.
- `bug`: Deep-dive into a tricky bug, root cause analysis, and the patch.
- `architecture`: Deep-dive into memory layouts, IPC, allocators, and trade-offs.
- `tech_stack`: Why specific languages, libraries, and architectures were chosen.
- `showcase`: Feature showcase emphasizing visuals, UI, and demos.

### 4. Review Existing Drafts

Drafts are automatically saved to `storage/drafts/draft_<id>_<repo>.md`. View any draft by ID:

```bash
larpflow show <draft_id>
```

### 5. Dispatch / Publish a Draft

```bash
# Post to all configured platforms
larpflow send <draft_id> --yes

# Post to specific platforms only
larpflow send <draft_id> -p linkedin,discord --yes

# Post with custom media override
larpflow send <draft_id> --image /path/to/demo.png --yes
```

### 6. Inspect Repos & History

```bash
# List your GitHub repositories
larpflow repos

# View recent drafts and delivery status
larpflow history

# Generate a fresh GitHub profile README from your repos
larpflow readme
```

---

## 🤖 Using LarpFlow with Antigravity / AI Agents

LarpFlow includes a bundled skill definition in [`skills/larp/SKILL.md`](skills/larp/SKILL.md).

### Antigravity Setup
Symlink or copy the skill into your Antigravity skills directory:

```bash
mkdir -p ~/.gemini/config/skills/larp
cp skills/larp/SKILL.md ~/.gemini/config/skills/larp/SKILL.md
```

Then in your Antigravity chat:
- Type `/larp <repo_name>`
- Or ask in natural language:
  - *"Run larpflow on my-repo focusing on the latest bug fix."*
  - *"Larp about Lyricora on LinkedIn and Discord."*
  - *"Check larpflow doctor and show my recent post history."*

---

## 📱 Optional: Telegram Approval Bot

If you prefer approving drafts from your phone via Telegram inline buttons:

1. Create a bot with `@BotFather` and paste the token in `TELEGRAM_BOT_TOKEN`.
2. Start the orchestrator:
   ```bash
   python -m core.agent_orchestrator
   ```
3. Send `/whoami` to your bot in Telegram, copy your user ID into `TELEGRAM_OWNER_ID` in `.env`, and restart.
4. Send `/run repo | problem | solution` in Telegram. Tap **Approve All**, **Edit Twitter**, or **Reject**.

---

## 📂 Project Structure

```
larpflow/
├── config/
│   ├── system_instructions.md    # LLM styling and anti-slop rules
│   ├── persona.example.json      # Template for developer facts & tone guardrails
│   └── linkedin_profile.example.md # Template for genuine LinkedIn voice
├── core/
│   ├── cli.py                    # Terminal CLI (run, send, show, repos, history)
│   ├── pipeline.py               # Ingest -> Draft -> Dispatch engine
│   ├── drafts.py                 # Multi-platform prompt crafting & rule validation
│   ├── llm.py                    # OpenAI/Gemini wrapper with fallback & timeouts
│   ├── config.py                 # Configuration loader & auto-detection
│   └── db.py                     # SQLite history storage
├── tools/
│   ├── tool_github.py            # GitHub API repo & commit diff extractor
│   ├── tool_x.py                 # X/Twitter v2 thread publisher + media upload
│   ├── tool_linkedin.py          # LinkedIn Posts & v2 UGC image uploader
│   ├── tool_reddit.py            # Reddit PRAW poster with flair auto-matching
│   ├── tool_discord.py           # Discord webhook rich embed publisher
│   └── tool_facebook.py          # Facebook Pages Graph API publisher
├── skills/
│   └── larp/SKILL.md             # Antigravity & Agent skill definition
├── storage/                      # SQLite database & rendered markdown drafts
├── .env.example                  # Environment template
└── pyproject.toml                # Package configuration & larpflow executable
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
