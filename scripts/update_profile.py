#!/usr/bin/env python3
"""Regenerate the dynamic parts of the profile README.

- assets/stats.svg : stat tiles, repos-by-language bar, animated contribution heatmap
- README.md        : the table between <!--RECENT:START--> and <!--RECENT:END-->

Standard library only. Needs GITHUB_TOKEN (or GH_TOKEN) in the environment.
"""
import datetime as dt
import json
import os
import pathlib
import re
import sys
import urllib.request
from xml.sax.saxutils import escape

LOGIN = os.environ.get("PROFILE_LOGIN") or os.environ.get("GITHUB_REPOSITORY_OWNER") or "Sarthak702-droid"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
ROOT = pathlib.Path(__file__).resolve().parent.parent

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      nodes { name url description pushedAt primaryLanguage { name } }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

# Colour follows the language, never its rank, so the bar does not repaint
# when the ordering changes. Anything not listed folds into "Other".
LANG_COLORS = {
    "Python": "#3987e5",
    "TypeScript": "#d95926",
    "Jupyter Notebook": "#199e70",
    "HTML": "#c98500",
    "Go": "#d55181",
    "Rust": "#9085e9",
    "JavaScript": "#e66767",
}
OTHER_COLOR = "#77777b"
HEAT = ["#26262a", "#104281", "#1c5cab", "#3987e5", "#86b6ef"]  # empty, then low -> high

SURFACE, TILE, BORDER = "#161617", "#1f1f22", "#2f2f31"
TEXT, TEXT2, MUTED = "#f0efec", "#c3c2b7", "#8b8b8d"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"


def fetch():
    if not TOKEN:
        sys.exit("GITHUB_TOKEN is not set")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-readme-updater"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors") or not body.get("data", {}).get("user"):
        sys.exit(f"GraphQL error: {body.get('errors')}")
    return body["data"]["user"]


def level_fn(days):
    nonzero = sorted(c for _, c in days if c)
    if not nonzero:
        return lambda c: 0
    q = [nonzero[min(len(nonzero) - 1, len(nonzero) * i // 4)] for i in (1, 2, 3)]

    def level(c):
        if c == 0:
            return 0
        return 1 + sum(c > t for t in q)

    return level


def render_svg(user):
    repos = user["repositories"]
    cal = user["contributionsCollection"]["contributionCalendar"]
    weeks = cal["weeks"]
    days = [(d["date"], d["contributionCount"]) for w in weeks for d in w["contributionDays"]]
    active = sum(1 for _, c in days if c)
    level = level_fn(days)

    counts = {}
    for r in repos["nodes"]:
        name = (r["primaryLanguage"] or {}).get("name")
        key = name if name in LANG_COLORS else "Other"
        counts[key] = counts.get(key, 0) + 1
    langs = sorted((k for k in counts if k != "Other"), key=lambda k: -counts[k])
    if counts.get("Other"):
        langs.append("Other")
    total = sum(counts.values()) or 1

    W, PAD = 840, 28
    inner = W - 2 * PAD
    out = []
    add = out.append

    # --- stat tiles -------------------------------------------------------
    tiles = [
        (repos["totalCount"], "public repositories"),
        (cal["totalContributions"], "contributions, last 12 months"),
        (active, "active days, last 12 months"),
        (len({r["primaryLanguage"]["name"] for r in repos["nodes"] if r["primaryLanguage"]}), "languages in use"),
    ]
    gap = 12
    tw = (inner - gap * (len(tiles) - 1)) / len(tiles)
    for i, (value, label) in enumerate(tiles):
        x = PAD + i * (tw + gap)
        add(f'<g class="fade" style="animation-delay:{i * 120}ms">'
            f'<rect x="{x:.1f}" y="56" width="{tw:.1f}" height="78" rx="10" fill="{TILE}" stroke="{BORDER}"/>'
            f'<text x="{x + 16:.1f}" y="94" font-size="28" font-weight="700" fill="{TEXT}">{value:,}</text>'
            f'<text x="{x + 16:.1f}" y="117" font-size="11.5" fill="{TEXT2}">{escape(label)}</text></g>')

    # --- repos by primary language ----------------------------------------
    add(f'<text x="{PAD}" y="170" font-size="12" font-weight="600" fill="{TEXT2}" letter-spacing=".6">'
        f'REPOSITORIES BY PRIMARY LANGUAGE</text>')
    add(f'<clipPath id="bar"><rect x="{PAD}" y="182" width="0" height="12" rx="4">'
        f'<animate attributeName="width" from="0" to="{inner}" dur="1.2s" begin="0.3s" fill="freeze" '
        f'calcMode="spline" keySplines=".2 .8 .2 1" keyTimes="0;1"/></rect></clipPath>')
    add('<g clip-path="url(#bar)">')
    x = PAD
    seg_gap = 2
    usable = inner - seg_gap * (len(langs) - 1)
    for name in langs:
        w = usable * counts[name] / total
        color = LANG_COLORS.get(name, OTHER_COLOR)
        add(f'<rect x="{x:.1f}" y="182" width="{w:.1f}" height="12" fill="{color}">'
            f'<title>{escape(name)}: {counts[name]} repos</title></rect>')
        x += w + seg_gap
    add('</g>')
    col = inner / max(len(langs), 1)
    for i, name in enumerate(langs):
        lx = PAD + i * col
        color = LANG_COLORS.get(name, OTHER_COLOR)
        label = "Jupyter" if name == "Jupyter Notebook" else name
        add(f'<rect x="{lx:.1f}" y="210" width="10" height="10" rx="2" fill="{color}"/>'
            f'<text x="{lx + 16:.1f}" y="219" font-size="12" fill="{TEXT}">{escape(label)} '
            f'<tspan fill="{MUTED}">{counts[name]}</tspan></text>')

    # --- contribution heatmap ---------------------------------------------
    add(f'<text x="{PAD}" y="262" font-size="12" font-weight="600" fill="{TEXT2}" letter-spacing=".6">'
        f'CONTRIBUTIONS, LAST 12 MONTHS</text>')
    step, cell = 14, 11
    gx = PAD + (inner - (len(weeks) * step - (step - cell))) / 2
    gy = 292
    last_month = None
    last_label_x = -100
    for wi, week in enumerate(weeks):
        first = dt.date.fromisoformat(week["contributionDays"][0]["date"])
        x = gx + wi * step
        if first.month != last_month:
            if last_month is not None and x - last_label_x > 30:
                add(f'<text x="{x:.1f}" y="{gy - 8}" font-size="10.5" fill="{MUTED}">{first.strftime("%b")}</text>')
                last_label_x = x
            last_month = first.month
        add(f'<g class="pop" style="animation-delay:{600 + wi * 22}ms">')
        for d in week["contributionDays"]:
            date = dt.date.fromisoformat(d["date"])
            row = (date.weekday() + 1) % 7  # Sunday on top, like github.com
            c = d["contributionCount"]
            add(f'<rect x="{x:.1f}" y="{gy + row * step}" width="{cell}" height="{cell}" rx="2.5" '
                f'fill="{HEAT[level(c)]}"><title>{d["date"]}: {c}</title></rect>')
        add('</g>')
    ly = gy + 7 * step + 16
    lx = W - PAD - (5 * step) - 78
    add(f'<text x="{lx}" y="{ly}" font-size="10.5" fill="{MUTED}">Less</text>')
    for i, color in enumerate(HEAT):
        add(f'<rect x="{lx + 30 + i * step}" y="{ly - 9.5}" width="{cell}" height="{cell}" rx="2.5" fill="{color}"/>')
    add(f'<text x="{lx + 34 + 5 * step}" y="{ly}" font-size="10.5" fill="{MUTED}">More</text>')

    H = ly + 22
    today = dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y")
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'font-family="{FONT}" role="img" aria-label="GitHub activity for {escape(LOGIN)}: '
        f'{repos["totalCount"]} public repositories, {cal["totalContributions"]} contributions in the last 12 months">'
        '<style>'
        '.fade{opacity:0;animation:fade .6s ease-out forwards}'
        '.pop{opacity:0;animation:pop .45s ease-out forwards}'
        '.live{animation:pulse 2s ease-in-out infinite}'
        '@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}'
        '@keyframes pop{from{opacity:0}to{opacity:1}}'
        '@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}'
        '@media (prefers-reduced-motion:reduce){.fade,.pop{animation:none;opacity:1}.live{animation:none}}'
        '</style>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="{SURFACE}" stroke="{BORDER}"/>'
        f'<circle class="live" cx="{PAD + 4}" cy="31" r="4" fill="#199e70"/>'
        f'<text x="{PAD + 16}" y="35" font-size="12" font-weight="600" fill="{TEXT2}" letter-spacing=".6">'
        f'LIVE FROM THE GITHUB API</text>'
        f'<text x="{W - PAD}" y="35" font-size="11.5" fill="{MUTED}" text-anchor="end">refreshed {today}</text>'
    )
    return head + "".join(out) + "</svg>\n"


def render_recent(user, limit=5):
    rows = ["| Repository | What it is | Stack | Last push |", "|---|---|---|---|"]
    # Repos without a description say nothing useful here, so they are skipped.
    picked = [r for r in user["repositories"]["nodes"]
              if r["name"].lower() != LOGIN.lower() and (r["description"] or "").strip()][:limit]
    for r in picked:
        desc = re.sub(r"[*_`|]", "", (r["description"] or "").strip()) or "—"
        if len(desc) > 120:
            desc = desc[:117].rsplit(" ", 1)[0] + "…"
        lang = (r["primaryLanguage"] or {}).get("name") or "—"
        date = dt.datetime.fromisoformat(r["pushedAt"].replace("Z", "+00:00")).strftime("%d %b %Y")
        lang = f"`{lang}`" if lang != "—" else lang
        rows.append(f"| [**{r['name']}**]({r['url']}) | {desc} | {lang} | {date} |")
    return "\n".join(rows)


def main():
    user = fetch()
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "stats.svg").write_text(render_svg(user), encoding="utf-8")

    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    block = f"<!--RECENT:START-->\n{render_recent(user)}\n<!--RECENT:END-->"
    new, n = re.subn(r"<!--RECENT:START-->.*?<!--RECENT:END-->", lambda _: block, text, flags=re.S)
    if n:
        readme.write_text(new, encoding="utf-8")
    else:
        print("warning: RECENT markers not found in README.md", file=sys.stderr)
    print("profile assets updated")


if __name__ == "__main__":
    main()
