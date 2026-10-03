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
    linkedin: str
    discord_title: str
    discord_body: str
    github_readme_section: str


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


def build_user_prompt(info, problem, solution, past_text):
    facts = json.dumps(info, indent=2)[:12000]
    return f"""REPO FACTS (from the GitHub API, the only ground truth about the code):
{facts}

WHAT THE DEV SAYS
Problem: {problem}
Solution: {solution}

ALREADY POSTED ABOUT THIS REPO (do not repeat these angles):
{past_text or "nothing yet"}

ALLOWED SUBREDDITS: {config.REDDIT_ALLOWED_SUBS}

Return ONLY one JSON object with these keys:
- "tweets": list of exactly 4 strings, each 275 characters or fewer. Tweet 4 contains {PLACEHOLDER}.
- "reddit_subreddit": one name from the allowed list, no "r/".
- "reddit_title": a plain, honest title.
- "reddit_body": markdown with the headers "### The Bottleneck", "### What Failed", "### The Fix". No links.
- "linkedin": 150 to 320 words, max 4 hashtags. Structure it logically: Project & scope, the specific problem/bottleneck encountered, the engineering solution, and concrete takeaways/problem-solving techniques used. May contain {PLACEHOLDER} once.
- "discord_title": short.
- "discord_body": 1500 characters or fewer.
- "github_readme_section": markdown with "Why this exists", "How it works", "Technical trade-offs".
Do not invent numbers. If something was not measured, say so."""



# ---------- generators ----------

def generate(info, problem, solution, past_text=""):
    system = build_system_prompt()
    user = build_user_prompt(info, problem, solution, past_text)
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
    return f"""DRAFT #{draft_id} for {repo}
{mode}
=== X THREAD ===
{tweets}

=== REDDIT r/{d.reddit_subreddit} ===
Title: {d.reddit_title}

{d.reddit_body}

=== LINKEDIN ({len(d.linkedin.split())} words) ===
{d.linkedin}

=== DISCORD ===
{d.discord_title}
{d.discord_body}

=== GITHUB README SECTION (copy/paste yourself) ===
{d.github_readme_section}
"""
