"""Agent 2 (the stylist): turns repo facts into drafts and checks the rules."""
import json
import re

from pydantic import BaseModel

from . import config, llm

PLACEHOLDER = "{REPO_URL}"
LINK_LEN = 23  # X counts every link as 23 characters
REDDIT_HEADERS = ["### The Bottleneck", "### What Failed", "### The Fix"]


class Drafts(BaseModel):
    tweets: list[str] = []
    reddit_subreddit: str = ""
    reddit_title: str = ""
    reddit_body: str = ""
    suggested_subreddits: list[str] = []
    linkedin: str = ""
    facebook: str = ""
    discord_title: str = ""
    discord_body: str = ""
    github_readme_section: str = ""
    visual_asset: str = ""  # Chosen image URL or suggested visual hook


VALID_PLATFORMS = {"x", "reddit", "linkedin", "discord", "facebook", "github"}


def normalize_platforms(platforms):
    if not platforms:
        return None
    if isinstance(platforms, str):
        raw = [p.strip().lower() for p in platforms.split(",") if p.strip()]
    else:
        raw = [p.strip().lower() for p in platforms if p]
    normalized = set()
    for p in raw:
        if p in ("twitter", "tweet", "tweets"):
            normalized.add("x")
        elif p in VALID_PLATFORMS:
            normalized.add(p)
    return normalized or None



# ---------- checks ----------

def tweet_len(text):
    text = text.replace(PLACEHOLDER, "x" * LINK_LEN)
    return len(re.sub(r"https?://\S+", "x" * LINK_LEN, text))


def tweet_problems(tweets):
    out = []
    if len(tweets) != 4:
        out.append(f"need exactly 4 tweets, got {len(tweets)}")
    for i, tweet in enumerate(tweets, 1):
        n = tweet_len(tweet)
        if n == 0:
            out.append(f"tweet {i} is empty")
        elif n > 275:
            out.append(f"tweet {i} is {n} characters (max 275)")
    return out


def banned_phrases():
    persona = config.load_persona()
    return persona["developer"]["tone_guardrails"]["do_not_use"]


def platform_problems(d, platforms=None):
    """Categorizes validation errors by platform name."""
    target = normalize_platforms(platforms) or VALID_PLATFORMS
    by_platform = {}

    def add_issue(platform, issue):
        by_platform.setdefault(platform, []).append(issue)

    # 1. X (Twitter)
    if "x" in target:
        if not d.tweets:
            add_issue("x", "tweets list is missing")
        else:
            for p in tweet_problems(d.tweets):
                add_issue("x", p)

    # 2. LinkedIn
    if "linkedin" in target:
        words = len(d.linkedin.split())
        if not 140 <= words <= 350:
            add_issue("linkedin", f"linkedin post is {words} words (need 140 to 350)")
        if len(re.findall(r"#\w+", d.linkedin)) > 4:
            add_issue("linkedin", "linkedin has more than 4 hashtags")

    # 3. Reddit
    if "reddit" in target:
        for header in REDDIT_HEADERS:
            if header not in d.reddit_body:
                add_issue("reddit", f"reddit body is missing the header '{header}'")
        if re.search(r"https?://|www\.", d.reddit_body, flags=re.I):
            add_issue("reddit", "reddit body must not contain links")
        if len(d.reddit_title) > 300:
            add_issue("reddit", "reddit title is longer than 300 characters")
        allowed = [s.lower() for s in config.REDDIT_ALLOWED_SUBS]
        if d.reddit_subreddit.lower() not in allowed:
            add_issue("reddit", f"subreddit must be one of {config.REDDIT_ALLOWED_SUBS}")

    # 4. Discord
    if "discord" in target:
        if len(d.discord_body) > 1500:
            add_issue("discord", "discord body is longer than 1500 characters")

    # 5. Check tone guardrails / banned phrases per platform
    banned = banned_phrases()
    if banned:
        platform_texts = {
            "x": " ".join(d.tweets).lower() if d.tweets else "",
            "linkedin": d.linkedin.lower() if d.linkedin else "",
            "reddit": f"{d.reddit_title} {d.reddit_body}".lower() if d.reddit_body else "",
            "discord": f"{d.discord_title} {d.discord_body}".lower() if d.discord_body else "",
            "facebook": d.facebook.lower() if d.facebook else "",
            "github": d.github_readme_section.lower() if d.github_readme_section else "",
        }
        for plat, text in platform_texts.items():
            if plat in target and text:
                for phrase in banned:
                    if phrase.lower() in text:
                        add_issue(plat, f"remove the banned phrase '{phrase}'")

    return by_platform


def problems(d, platforms=None):
    """Returns a flat list of issues across all target platforms."""
    by_plat = platform_problems(d, platforms=platforms)
    return [issue for issues in by_plat.values() for issue in issues]


# ---------- prompts ----------

def build_system_prompt():
    parts = [config.load_system_prompt(), "# PERSONA (ground truth about the dev)", json.dumps(config.load_persona(), indent=2)]
    linkedin = config.load_linkedin_profile()
    if linkedin:
        parts += ["# LINKEDIN PROFILE (pasted by the dev, ground truth)", linkedin]
    return "\n\n".join(parts)


def build_user_prompt(info, problem, solution, past_text, post_type="auto", platforms=None):
    facts = json.dumps(info, indent=2)[:12000]
    images = info.get("images", [])
    images_text = json.dumps(images, indent=2) if images else "none found in repo"
    target = normalize_platforms(platforms) or VALID_PLATFORMS

    narrative_focus = {
        "intro": "FOCUS: Casual, high-level project introduction. NO low-level architecture or internal system algorithms (no mentioning IPC, notification buses, allocators, or math formulas). Focus on: what the app does, who it's for, the visual vibe, and the user experience. Showcase images/visuals if available.",
        "motivation": "FOCUS: The personal motive, inspiration, and user story. NO deep-dive system internals or low-level algorithms. Explain: why you wanted this, why existing tools (like default Spotify) felt bland/lacking, the vision for building it, and how it feels to use. Keep it relatable, human, and product-focused.",
        "bug": "FOCUS: Deep-dive into a specific technical bug or bottleneck, how it was diagnosed, the exact patch/fix, and concrete lessons learned.",
        "architecture": "FOCUS: Full system architecture, deep-dive into internal event loops, IPC/notification buses, memory layouts, allocators, and technical trade-offs.",
        "full_project": "FOCUS: Comprehensive overview of the full project, its architecture, what it accomplishes, core design decisions, and tradeoffs.",
        "tech_stack": "FOCUS: Deep dive into the technologies, allocators/memory structures, libraries, and exact reason this stack was chosen over alternatives.",
        "showcase": "FOCUS: Direct, energetic project showcase emphasizing key features, visual capabilities, and hands-on usage demos.",
    }.get(post_type.lower(), "FOCUS: Balance between project scope, real bottleneck/problem, the technical solution, and concrete engineering takeaways.")

    guidelines = []
    if "x" in target:
        guidelines.append("1. X (Twitter): Focus on project showcase or short, punchy bug overviews. NEVER dive into deep technical jargon or mathematical formulas unless explicitly instructed. Keep it visual and engaging.")
    if "reddit" in target or "facebook" in target:
        guidelines.append("2. Reddit & Facebook: Engaging project showcase with clear context. For Reddit, follow default or specified subreddits and provide 2-3 relevant suggested subreddits for this specific topic. Include technical breakdown and lessons learned. For Facebook, write an engaging, community-friendly showcase post (100-250 words) with clean line breaks.")
    if "discord" in target:
        guidelines.append("3. Discord: Very simple, casual project showcase. Bullet points of what it is and what it does. Keep it lightweight and conversational.")

    platform_defaults = "\n".join(guidelines)
    if platform_defaults:
        platform_defaults = f"PLATFORM GUIDELINES FOR REQUESTED PLATFORMS:\n{platform_defaults}\n"

    key_descriptions = []
    if "x" in target:
        key_descriptions.append(f'- "tweets": list of exactly 4 strings, each 275 characters or fewer. Tweet 4 contains {PLACEHOLDER}. Showcase/overview style, avoid deep technical algorithms unless asked.')
    if "reddit" in target:
        key_descriptions.extend([
            '- "reddit_subreddit": one primary name from allowed list or best matching subreddit, no "r/".',
            '- "suggested_subreddits": list of 2-3 recommended subreddits relevant to this project/topic.',
            '- "reddit_title": a plain, honest title matching the requested narrative focus.',
            '- "reddit_body": markdown with the headers "### The Bottleneck", "### What Failed", "### The Fix". No links.',
        ])
    if "linkedin" in target:
        key_descriptions.append(f'- "linkedin": 150 to 320 words, max 4 hashtags. Structure it logically: Project & scope, the specific problem/bottleneck encountered, the engineering solution, and concrete takeaways/problem-solving techniques used. May contain {PLACEHOLDER} once.')
    if "facebook" in target:
        key_descriptions.append(f'- "facebook": 100 to 250 words community showcase post with clean paragraphs and project link {PLACEHOLDER}.')
    if "discord" in target:
        key_descriptions.extend([
            '- "discord_title": short.',
            '- "discord_body": 1500 characters or fewer. Simple, casual project showcase.',
        ])
    if "github" in target:
        key_descriptions.append('- "github_readme_section": markdown with "Why this exists", "How it works", "Technical trade-offs".')

    key_descriptions.append('- "visual_asset": pick the most relevant image URL from the available images above (or suggest a short descriptive visual prompt for a GIF/screenshot if none exist).')
    keys_str = "\n".join(key_descriptions)

    return f"""REPO FACTS (from the repository facts, the only ground truth about the code):
{facts}

AVAILABLE REPOSITORY IMAGES & MEDIA:
{images_text}

NARRATIVE ANGLE REQUESTED:
{narrative_focus}

{platform_defaults}
WHAT THE DEV SAYS
Problem / Context: {problem}
Solution / Implementation: {solution}

ALREADY POSTED ABOUT THIS REPO (do not repeat these angles):
{past_text or "nothing yet"}

ALLOWED SUBREDDITS: {config.REDDIT_ALLOWED_SUBS}

Return ONLY one JSON object with these keys for the requested platforms:
{keys_str}
Do not invent numbers. If something was not measured, say so."""


# ---------- generators ----------

def build_retry_prompt(d, failed_platforms, issues_by_platform, info, problem, solution, post_type="auto"):
    """Constructs a targeted prompt to rewrite only the failing platform drafts."""
    issue_lines = []
    for plat in sorted(failed_platforms):
        issue_lines.append(f"Platform [{plat}] failed with:")
        for iss in issues_by_platform.get(plat, []):
            issue_lines.append(f"  - {iss}")

    key_descriptions = []
    if "x" in failed_platforms:
        key_descriptions.append(f'- "tweets": list of exactly 4 strings, each 275 characters or fewer. Tweet 4 contains {PLACEHOLDER}.')
    if "reddit" in failed_platforms:
        key_descriptions.extend([
            '- "reddit_subreddit": one primary name from allowed list or best matching subreddit, no "r/".',
            '- "reddit_title": a plain, honest title matching the requested narrative focus.',
            '- "reddit_body": markdown with headers "### The Bottleneck", "### What Failed", "### The Fix". No links.',
        ])
    if "linkedin" in failed_platforms:
        key_descriptions.append(f'- "linkedin": 150 to 320 words, max 4 hashtags. Structure: Project & scope, bottleneck, engineering solution, takeaways. May contain {PLACEHOLDER} once.')
    if "facebook" in failed_platforms:
        key_descriptions.append(f'- "facebook": 100 to 250 words community showcase post with clean paragraphs and {PLACEHOLDER}.')
    if "discord" in failed_platforms:
        key_descriptions.extend([
            '- "discord_title": short.',
            '- "discord_body": 1500 characters or fewer. Simple, casual project showcase.',
        ])
    if "github" in failed_platforms:
        key_descriptions.append('- "github_readme_section": markdown with "Why this exists", "How it works", "Technical trade-offs".')

    issues_str = "\n".join(issue_lines)
    keys_str = "\n".join(key_descriptions)

    return f"""The previous generation succeeded for other channels, but failed rules for: {', '.join(failed_platforms)}.

VALIDATION FAILURES TO FIX:
{issues_str}

CONTEXT:
Repository: {info.get('full_name')}
Problem: {problem}
Solution: {solution}

Please regenerate ONLY the failing platform field(s). Keep all rule constraints strictly intact.
Return ONLY one JSON object containing the corrected keys:
{keys_str}"""


def generate(info, problem, solution, past_text="", post_type="auto", platforms=None):
    system = build_system_prompt()
    user = build_user_prompt(info, problem, solution, past_text, post_type=post_type, platforms=platforms)

    # 1. Initial complete generation pass
    raw = llm.chat(system, user, json_mode=True)
    try:
        d = Drafts(**llm.parse_json(raw))
    except Exception:
        # If initial JSON parsing fails, retry once with explicit syntax nudge
        raw = llm.chat(system, user + "\n\nYour previous response was not valid JSON. Return valid JSON only.", json_mode=True)
        d = Drafts(**llm.parse_json(raw))

    d.reddit_subreddit = d.reddit_subreddit.replace("r/", "").strip()
    by_plat = platform_problems(d, platforms=platforms)
    if not by_plat:
        return d

    # 2. Modular per-platform retries (surgically fixing only broken fields)
    for retry in range(3):
        failed_plats = list(by_plat.keys())
        retry_prompt = build_retry_prompt(d, failed_plats, by_plat, info, problem, solution, post_type=post_type)
        raw_fix = llm.chat(system, retry_prompt, json_mode=True)

        try:
            fix_json = llm.parse_json(raw_fix)
            # Surgically patch only the failing platform fields into d
            for key, val in fix_json.items():
                if hasattr(d, key) and val:
                    if key == "reddit_subreddit":
                        val = str(val).replace("r/", "").strip()
                    setattr(d, key, val)
        except Exception:
            pass

        by_plat = platform_problems(d, platforms=platforms)
        if not by_plat:
            return d

    flat_issues = [issue for issues in by_plat.values() for issue in issues]
    raise ValueError("The model kept breaking the rules on platforms (" + ", ".join(by_plat.keys()) + "): " + "; ".join(flat_issues))


def generate_profile_readme(repos):
    system = build_system_prompt()
    user = f"""Write the GitHub profile README.md for {config.GITHUB_USER}.

His public repos (ground truth, do not add projects that are not here):
{json.dumps(repos, indent=2)[:12000]}

Rules:
- Short intro from the persona and LinkedIn text only.
- A project list with a link and one honest line each. Skip repos with no description unless you can tell what they are from the name.
- A short stack section from the persona.
- A line linking to his LinkedIn.
- No fake stats, no badges walls, no buzzwords.
Return only the markdown."""
    text = llm.chat(system, user, temperature=0.5).strip()
    return re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", text)


def render_preview(draft_id, repo, d, platforms=None):
    target = normalize_platforms(platforms)
    sections = []

    if (not target or "x" in target) and d.tweets:
        tweets = "\n\n".join(f"[{i}/{len(d.tweets)}] {t}" for i, t in enumerate(d.tweets, 1))
        sections.append(f"=== X THREAD ===\n{tweets}")

    if (not target or "reddit" in target) and d.reddit_body:
        subs_info = f" (Suggested subs: {', '.join(d.suggested_subreddits)})" if d.suggested_subreddits else ""
        sections.append(f"=== REDDIT r/{d.reddit_subreddit}{subs_info} ===\nTitle: {d.reddit_title}\n\n{d.reddit_body}")

    if (not target or "linkedin" in target) and d.linkedin:
        sections.append(f"=== LINKEDIN ({len(d.linkedin.split())} words) ===\n{d.linkedin}")

    if (not target or "facebook" in target) and d.facebook:
        sections.append(f"=== FACEBOOK ===\n{d.facebook}")

    if (not target or "discord" in target) and d.discord_body:
        sections.append(f"=== DISCORD ===\n{d.discord_title}\n{d.discord_body}")

    if (not target or "github" in target) and d.github_readme_section:
        sections.append(f"=== GITHUB README SECTION (copy/paste or push directly) ===\n{d.github_readme_section}")

    mode = "DRY RUN is ON, nothing will really post.\n" if config.DRY_RUN else "LIVE MODE: Approve will post for real.\n"
    visual = f"🖼️ VISUAL / IMAGE: {d.visual_asset}\n" if d.visual_asset else ""
    body = "\n\n".join(sections) if sections else "No platform sections generated."

    return f"""DRAFT #{draft_id} for {repo}
{mode}{visual}
{body}
"""


