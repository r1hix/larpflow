# LarpFlow

A small tool that reads your GitHub repos and helps you post about them on X, Reddit, LinkedIn and Discord.

You tell it what broke and how you fixed it. It reads the repo, writes a draft for each platform, and sends the drafts to your Telegram. **Nothing gets posted until you tap Approve.**

---

## What it does

1. You send `/run repo | problem | solution` to your Telegram bot.
2. It pulls the README, file list, recent commits, diffs and closed issues from GitHub.
3. An LLM writes drafts for every platform, using only real facts from the repo and your own words.
4. The code checks the drafts (tweet length, word count, banned buzzwords, Reddit headers). If a rule is broken, the model has to redo it.
5. The drafts show up in Telegram with three buttons: **Approve All**, **Edit Twitter**, **Reject**.
6. On Approve it posts, and saves everything in a local history database.

```
 Telegram /run
      |
      v
 [1 GitHub Ingestor] --> repo facts
      |
      v
 [2 Stylist (LLM)] --> drafts --> rule checker (retry up to 3x)
      |
      v
 [3 Gatekeeper] --> Telegram buttons --> YOU decide
      |
   Approve
      v
 [4 Dispatcher] --> X thread / Reddit / LinkedIn / Discord
      |
      v
 storage/history.sqlite
```

The "agents" are just four normal pieces of code. Only the Stylist calls an LLM.

---

## The platforms (what each one is for)

| Platform | What gets posted | Style |
|----------|------------------|-------|
| **X** | 4-tweet thread: hook, the bottleneck, the fix, link and "try to break it" | short, punchy, one idea per tweet |
| **Reddit** | One post-mortem with `The Bottleneck`, `What Failed`, `The Fix`. No links in the body. | humble, detailed |
| **LinkedIn** | 150 to 250 words, max 3 hashtags | problem breakdown, lessons, clean code and reliability |
| **Discord** | A rich embed dev-log through a webhook | casual showcase message |
| **GitHub** | Direct commit & push of Architecture & Trade-offs to repo README, plus profile README | automated or manual |


---

## Folder map

```
larpflow/
  config/
    system_instructions.md   the rules the LLM follows
    persona.json             your real stack and banned phrases
    linkedin_profile.md      paste your LinkedIn text here
  core/
    agent_orchestrator.py    the Telegram bot
    cli.py                   same thing in the terminal
    pipeline.py              ingest -> draft -> dispatch
    drafts.py                prompts and rule checks
    llm.py                   talks to the LLM API
    db.py                    history (sqlite)
    config.py                reads .env
  tools/
    tool_github.py  tool_telegram.py  tool_x.py
    tool_reddit.py  tool_linkedin.py  tool_discord.py
  storage/                   history.sqlite lives here (git ignored)
  .env.example               copy to .env
  requirements.txt
```

---

## Setup

### 1. Run the build script

```bash
python build_larpflow.py
cd larpflow
```

It makes the folders, writes the files, creates a virtual environment, installs the packages, copies `.env.example` to `.env` and runs `git init`.
Useful flags: `--no-install` (skip the venv and pip), `--force` (overwrite files that already exist), and you can pass a different folder name as the first argument.

Then activate the venv:

```bash
source venv/bin/activate        # Mac / Linux
venv\Scripts\activate           # Windows
```

### 2. Fill in `.env`

You don't need everything on day one. Start with these:

- `LLM_API_KEY` (and `LLM_BASE_URL` plus `LLM_MODEL` if you use Gemini or something else that isn't OpenAI)
- `TELEGRAM_BOT_TOKEN`

Check what's missing any time:

```bash
python -m core.cli doctor
```

Platforms without keys are skipped, so you can add X, Reddit, LinkedIn and Discord one by one.

### 3. Where to get the keys

- **Telegram:** talk to `@BotFather`, send `/newbot`, copy the token. Then start the bot (step 4), send it `/whoami`, and put the number in `TELEGRAM_OWNER_ID`. Restart. Only that id can use the bot.
- **GitHub token (optional):** Settings, Developer settings, Personal access tokens. Read-only is enough. Needed for private repos and to avoid rate limits.
- **X:** developer portal, make an app, set permissions to **Read and Write**, then generate the API key, secret, access token and access token secret. Generate the access token *after* changing permissions or it stays read-only.
- **Reddit:** `reddit.com/prefs/apps`, create an app of type **script**. The client id is under the app name. The secret is the "secret" field.
- **LinkedIn:** `developers.linkedin.com`, create an app, add the "Share on LinkedIn" product, and get an access token with the `w_member_social` scope. Your person URN looks like `urn:li:person:XXXX`. Tokens expire, so you will refresh it now and then. LinkedIn changes things often, so trust their docs if a step looks different.
- **Discord:** Channel settings, Integrations, Webhooks, New Webhook, Copy URL.

### 4. Fill in your persona and LinkedIn text

- Open `config/persona.json` and check the stack list. This is what stops the model from making up skills. Edit it so it's actually true.
- Open `config/linkedin_profile.md` and paste your headline, About, experience and a few old posts you liked. LinkedIn can't be scraped (it's against their rules and can get you banned), so this is the safe way to give the drafts your real background and voice.

### 5. Run it

```bash
python -m core.agent_orchestrator
```

Then in Telegram:

```
/run tank-sim | Fast mouse sweeps desynced the turret angle from frame updates | Replaced raw frame coordinates with normalized lerp angle interpolation over delta time
```

(That one is just an example. Use your own repo name.)

No Telegram yet? Use the terminal version:

```bash
python -m core.cli run "tank-sim | the problem | the fix"
python -m core.cli send 1
```

---

## Commands

| Command | What it does |
|---------|--------------|
| `/run repo \| problem \| solution` | Make drafts for a repo |
| `/repos` | List your GitHub repos |
| `/history` | See past drafts and where they were posted |
| `/readme` | Write a new GitHub profile README from your repos and send it as a file |
| `/whoami` | Show your Telegram id |
| `/cancel` | Stop editing tweets |

**Edit Twitter:** tap the button, then send the 4 new tweets in one message with a line containing just `---` between them. The bot checks the length before saving.

---

## Dry run (important)

`DRY_RUN=true` is the default. Drafts are made and Approve "works", but nothing is posted. The audit message just says "would post".

Run it like this for a while, read the drafts, then set `DRY_RUN=false` when you trust them.

---

## History

Every draft and every post result is saved in `storage/history.sqlite`.

- The model sees what you already posted about a repo, so it won't repeat the same angle.
- If a post fails halfway (say X works but Reddit errors), run Approve again. Platforms that already worked are skipped, so nothing double posts.
- GitHub history comes live from the API every time you run. LinkedIn history comes from the text you paste in `config/linkedin_profile.md`.

---

## Your profile README

Your profile README lives in a repo named exactly like your username (`r1hix/r1hix`), in a file called `README.md`. Send `/readme` (or run `python -m core.cli readme`) and you get a fresh one written from your repos. Check it, then paste it in yourself.

---

## Rules of the road

- **Reddit:** most subs hate self-promo. Read each sub's rules before you add it to `REDDIT_ALLOWED_SUBS`. Only one subreddit is used per draft, on purpose. Don't post the same thing everywhere on the same day. Some subs also need a post flair, and the API call will fail there.
- **X and LinkedIn:** don't spam. A thread per real milestone is plenty.
- **Numbers:** the model is told not to invent benchmarks. If you want numbers in a post, put them in your `problem` or `solution` text.
- **Always read the draft.** It's a draft, not a ghostwriter. Fix anything that doesn't sound like you.
- **Keep `.env` private.** It's in `.gitignore`. Never commit it.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot doesn't answer | `TELEGRAM_OWNER_ID` is empty or wrong. Send `/whoami` and fix it. |
| "Repo not found" | Typo in the name, or the repo is private and `GITHUB_TOKEN` is empty. |
| "The model kept breaking the rules" | Try again, or use a stronger model in `LLM_MODEL`. |
| X says 403 | Your app is read-only. Set Read and Write, then make a new access token. |
| LinkedIn says 401 | The token expired. Make a new one. |
| Reddit fails with a flair or rules error | That subreddit needs flair or blocks new accounts. Post that one by hand. |

---

## Using it with Antigravity (or any AI IDE)

This project runs on its own with plain Python. If you want to extend it with an AI coding agent, open the folder in your IDE and paste `config/system_instructions.md` in as the agent's instructions. Good first things to ask for: a scheduled "weekly dev-log" run, image or GIF attachments, or a LinkedIn Posts API swap if the old call stops working.
