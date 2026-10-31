---
name: larp
description: Generate factual developer dev-logs, technical post-mortems, X threads, Reddit posts, and LinkedIn updates from GitHub repos and commit diffs using LarpFlow.
---

# Larp (LarpFlow Dev-Log & Social Syndication Skill)

Use this skill whenever the user asks to create dev-logs, write technical drafts, post or preview updates for their GitHub repositories, or trigger `/larp`.

## Fast-Path Agent Instructions (CRITICAL):
1. **DO NOT over-think or pre-research the repo manually:** Do NOT browse files, search git logs, run subagents, or draft social posts yourself. LarpFlow has an internal GitHub ingestor, LLM stylist, and strict platform rule-validator. Immediately invoke `larpflow run` in a single command.
2. **One-Step Publish:** When the user asks to "larp about X on platforms" or post updates, run the all-in-one command:
   ```bash
   larpflow run <repo_name> --publish -p <platforms> --yes
   ```
   (e.g. `larpflow run Lyricora --publish -p linkedin,discord --yes`)
3. **Always use `--yes`:** Whenever running `larpflow send` or `--publish`, append `--yes` to avoid blocking on terminal `stdin` prompts in non-interactive sessions.
4. **Draft Previews:** If the user only wants to preview/draft first, run `larpflow run <repo_name>` and display the output or reference `storage/drafts/draft_<id>_<repo>.md`.

## Workflow & Commands

### 1. List Available Repositories
To inspect what repos are available:
```bash
larpflow repos
```

### 2. Generate Drafts for a Repository
Run LarpFlow on any repo with optional narrative type, commit depth, manual problem/solution, or custom media image:

**Auto-infer mode (Zero-prompt):**
```bash
larpflow run <repo_name>
```

**One-Step Draft & Publish:**
```bash
larpflow run <repo_name> --publish -p linkedin,discord --yes
```

**With Custom Image / Media Attachment:**
```bash
larpflow run <repo_name> --image /path/to/gameplay.png
```

**Narrative Types (`--type` / `-t`):**
- `intro`: Casual, high-level overview. What it is, who it's for, visual vibe, and user experience. **Zero low-level system jargon.**
- `motivation`: The personal backstory, inspiration, and why existing tools felt inadequate. Relatable and product-focused.
- `bug`: Tricky engineering bug, root cause analysis, and the exact patch fix.
- `architecture`: Deep-dive into internal event loops, IPC/notification buses, memory layouts, and allocators.
- `tech_stack`: Why this specific stack/allocator was chosen over alternatives.
- `showcase`: Energetic feature showcase emphasizing key demos and visuals.

**Platform Defaults When No Specific Options Are Given:**
1. **X (Twitter)**: Project showcase or short bug overview. High-level only, **never low-level technical jargon or math** unless explicitly specified. Automatically attaches local gameplay/screenshot images if found.
2. **Reddit & Facebook**: Engaging project showcase + technical lessons learned. Follows default/specified subreddits and suggests 2-3 tailored subreddits. Facebook post is community-friendly (100-250 words).
3. **Discord**: Very simple, casual project showcase bullet points with screenshot attachments.

**Auto-Open Drafts:**
Every `run` automatically writes a full preview file to `storage/drafts/draft_<id>_<repo>.md` and opens it in your editor for review before asking for approval. Pass `--no-open` to disable auto-open in automated sessions.

### 3. Review & Inspect Existing Drafts
View any previously created draft instantly by ID:
```bash
larpflow show <draft_id>
```

### 4. Dispatching (Posting)
Once approved:

**Post to all configured platforms:**
```bash
larpflow send <draft_id> --yes
```

**Post with custom media override:**
```bash
larpflow send <draft_id> --image /path/to/screenshot.png --yes
```

**Push architecture section directly to GitHub README:**
```bash
larpflow send <draft_id> -p github --yes
```

**Post to LinkedIn:**
```bash
larpflow send <draft_id> -p linkedin --yes
```

**Post to Facebook:**
```bash
larpflow send <draft_id> -p facebook --yes
```

### 5. Check Health & Configuration
```bash
larpflow doctor
```

