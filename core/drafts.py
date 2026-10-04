"""Agent 2 (the stylist): turns repo facts into drafts and checks the rules."""
import json
import re

from pydantic import BaseModel

from . import config, llm

PLACEHOLDER = "{REPO_URL}"
LINK_LEN = 23  # X counts every link as 23 characters
REDDIT_HEADERS = ["### The Bottleneck", "### What Failed", "### The Fix"]


class Drafts(BaseModel):
    tweets: list[str]
    reddit_subreddit: str
    reddit_title: str
    reddit_body: str
    suggested_subreddits: list[str] = []
    linkedin: str
    facebook: str = ""
    discord_title: str
    discord_body: str
    github_readme_section: str
    visual_asset: str = ""  # Chosen image URL or suggested visual hook



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


def problems(d):
    out = tweet_problems(d.tweets)

    words = len(d.linkedin.split())
    if not 140 <= words <= 350:
        out.append(f"linkedin post is {words} words (need 140 to 350)")
    if len(re.findall(r"#\w+", d.linkedin)) > 4:
        out.append("linkedin has more than 4 hashtags")

    for header in REDDIT_HEADERS:
        if header not in d.reddit_body:
            out.append(f"reddit body is missing the header '{header}'")
    if re.search(r"https?://|www\.", d.reddit_body, flags=re.I):
        out.append("reddit body must not contain links")
    if len(d.reddit_title) > 300:
        out.append("reddit title is longer than 300 characters")
    allowed = [s.lower() for s in config.REDDIT_ALLOWED_SUBS]
    if d.reddit_subreddit.lower() not in allowed:
        out.append(f"subreddit must be one of {config.REDDIT_ALLOWED_SUBS}")

    if len(d.discord_body) > 1500:
        out.append("discord body is longer than 1500 characters")

    blob = " ".join(
        d.tweets
        + [d.reddit_title, d.reddit_body, d.linkedin, d.discord_title, d.discord_body, d.github_readme_section]
    ).lower()
    for phrase in banned_phrases():
        if phrase.lower() in blob:
            out.append(f"remove the phrase '{phrase}'")
    return out


# ---------- prompts ----------

def build_system_prompt():
    parts = [config.load_system_prompt(), "# PERSONA (ground truth about the dev)", json.dumps(config.load_persona(), indent=2)]
    linkedin = config.load_linkedin_profile()
    if linkedin:
        parts += ["# LINKEDIN PROFILE (pasted by the dev, ground truth)", linkedin]
    return "\n\n".join(parts)


def build_user_prompt(info, problem, solution, past_text, post_type="auto"):
    facts = json.dumps(info, indent=2)[:12000]
    images = info.get("images", [])
    images_text = json.dumps(images, indent=2) if images else "none found in repo"

    narrative_focus = {
        "intro": "FOCUS: Casual, high-level project introduction. NO low-level architecture or internal system algorithms (no mentioning IPC, notification buses, allocators, or math formulas). Focus on: what the app does, who it's for, the visual vibe, and the user experience. Showcase images/visuals if available.",
        "motivation": "FOCUS: The personal motive, inspiration, and user story. NO deep-dive system internals or low-level algorithms. Explain: why you wanted this, why existing tools (like default Spotify) felt bland/lacking, the vision for building it, and how it feels to use. Keep it relatable, human, and product-focused.",
        "bug": "FOCUS: Deep-dive into a specific technical bug or bottleneck, how it was diagnosed, the exact patch/fix, and concrete lessons learned.",
        "architecture": "FOCUS: Full system architecture, deep-dive into internal event loops, IPC/notification buses, memory layouts, allocators, and technical trade-offs.",
        "full_project": "FOCUS: Comprehensive overview of the full project, its architecture, what it accomplishes, core design decisions, and tradeoffs.",
        "tech_stack": "FOCUS: Deep dive into the technologies, allocators/memory structures, libraries, and exact reason this stack was chosen over alternatives.",
        "showcase": "FOCUS: Direct, energetic project showcase emphasizing key features, visual capabilities, and hands-on usage demos.",
    }.get(post_type.lower(), "FOCUS: Balance between project scope, real bottleneck/problem, the technical solution, and concrete engineering takeaways.")


    platform_defaults = """
PLATFORM DEFAULT GUIDELINES:
1. X (Twitter): Focus on project showcase or short, punchy bug overviews. NEVER dive into deep technical jargon or mathematical formulas unless explicitly instructed. Keep it visual and engaging.
2. Reddit & Facebook: Engaging project showcase with clear context. For Reddit, follow default or specified subreddits and provide 2-3 relevant suggested subreddits for this specific topic. Include technical breakdown and lessons learned. For Facebook, write an engaging, community-friendly showcase post (100-250 words) with clean line breaks.
3. Discord: Very simple, casual project showcase. Bullet points of what it is and what it does. Keep it lightweight and conversational.
"""

    return f"""REPO FACTS (from the GitHub API, the only ground truth about the code):
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

Return ONLY one JSON object with these keys:
- "tweets": list of exactly 4 strings, each 275 characters or fewer. Tweet 4 contains {PLACEHOLDER}. Showcase/overview style, avoid deep technical algorithms unless asked.
- "reddit_subreddit": one primary name from allowed list or best matching subreddit, no "r/".
- "suggested_subreddits": list of 2-3 recommended subreddits relevant to this project/topic.
- "reddit_title": a plain, honest title matching the requested narrative focus.
- "reddit_body": markdown with the headers "### The Bottleneck", "### What Failed", "### The Fix". No links.
- "linkedin": 150 to 320 words, max 4 hashtags. Structure it logically: Project & scope, the specific problem/bottleneck encountered, the engineering solution, and concrete takeaways/problem-solving techniques used. May contain {PLACEHOLDER} once.
- "facebook": 100 to 250 words community showcase post with clean paragraphs and project link {PLACEHOLDER}.
- "discord_title": short.
- "discord_body": 1500 characters or fewer. Simple, casual project showcase.
- "github_readme_section": markdown with "Why this exists", "How it works", "Technical trade-offs".
- "visual_asset": pick the most relevant image URL from the available images above (or suggest a short descriptive visual prompt for a GIF/screenshot if none exist).
Do not invent numbers. If something was not measured, say so."""



# ---------- generators ----------

def generate(info, problem, solution, past_text="", post_type="auto"):
    system = build_system_prompt()
    user = build_user_prompt(info, problem, solution, past_text, post_type=post_type)
    issues = []
    for _ in range(3):
        prompt = user
        if issues:
            prompt += "\n\nYour last answer broke these rules. Fix them and send the full JSON again:\n- " + "\n- ".join(issues)
        raw = llm.chat(system, prompt, json_mode=True)
        try:
            d = Drafts(**llm.parse_json(raw))
        except ValueError as e:  # bad JSON or missing keys
            issues = [f"the answer was not valid: {e}"]
            continue
        d.reddit_subreddit = d.reddit_subreddit.replace("r/", "").strip()
        issues = problems(d)
        if not issues:
            return d
    raise ValueError("The model kept breaking the rules: " + "; ".join(issues))


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


def render_preview(draft_id, repo, d):
    tweets = "\n\n".join(f"[{i}/{len(d.tweets)}] {t}" for i, t in enumerate(d.tweets, 1))
    mode = "DRY RUN is ON, nothing will really post.\n" if config.DRY_RUN else "LIVE MODE: Approve will post for real.\n"
    visual = f"🖼️ VISUAL / IMAGE: {d.visual_asset}\n" if d.visual_asset else ""
    subs_info = f" (Suggested subs: {', '.join(d.suggested_subreddits)})" if d.suggested_subreddits else ""

    fb_section = ""
    if d.facebook:
        fb_section = f"\n=== FACEBOOK ===\n{d.facebook}\n"

    return f"""DRAFT #{draft_id} for {repo}
{mode}{visual}
=== X THREAD ===
{tweets}

=== REDDIT r/{d.reddit_subreddit}{subs_info} ===
Title: {d.reddit_title}

{d.reddit_body}

=== LINKEDIN ({len(d.linkedin.split())} words) ===
{d.linkedin}
{fb_section}
=== DISCORD ===
{d.discord_title}
{d.discord_body}

=== GITHUB README SECTION (copy/paste or push directly) ===
{d.github_readme_section}
"""


