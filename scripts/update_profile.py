#!/usr/bin/env python3
"""Regenerate the dynamic parts of the profile README.

- assets/stats.svg   : odometer stat tiles, repos-by-language bar, isometric contribution skyline
- assets/maze.svg    : a maze built from a seed word and solved by A*, animated
- assets/toolbox.svg : scrolling tech marquee
- README.md          : the blocks between <!--RECENT:*--> and <!--MAZE:*--> markers
- data/maze.json     : current maze seed and recent challengers

Standard library only. Needs GITHUB_TOKEN (or GH_TOKEN) in the environment.
A visitor sets the maze by opening an issue titled "maze: <word>"; the workflow
passes that title in MAZE_TITLE and the author in MAZE_BY.
"""
import datetime as dt
import heapq
import json
import math
import os
import pathlib
import random
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
HEAT = ["#2c2c31", "#104281", "#1c5cab", "#3987e5", "#86b6ef"]  # empty, then low -> high

SURFACE, TILE, BORDER = "#161617", "#1f1f22", "#2f2f31"
TEXT, TEXT2, MUTED = "#f0efec", "#c3c2b7", "#8b8b8d"
BLUE, GREEN = "#3987e5", "#199e70"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "SFMono-Regular, Menlo, Monaco, Consolas, monospace"

TOOLBOX = [
    ["Python", "TypeScript", "Go", "Rust", "JavaScript", "SQL"],
    ["scikit-learn", "pandas", "NumPy", "OpenCV", "YOLOv8", "Jupyter", "Power BI"],
    ["Next.js", "React", "PostgreSQL", "Redis", "Docker", "Git", "Open Policy Agent", "Razorpay"],
]


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


def shade(hex_color, factor):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v * factor))) for v in (r, g, b))


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


# ---------------------------------------------------------------- stats card

def odometer(value, x, y, delay):
    """Digits that roll up to their value. x, y is the top-left of the number."""
    out, adv, line = [], 17, 34
    for i, ch in enumerate(str(value)):
        d = int(ch)
        steps = 10 + d
        column = "".join(
            f'<text x="0" y="{27 + k * line}">{k % 10}</text>' for k in range(steps + 1))
        out.append(
            f'<svg x="{x + i * adv:.1f}" y="{y}" width="{adv}" height="{line}">'
            f'<g font-size="28" font-weight="700" fill="{TEXT}" style="font-variant-numeric:tabular-nums">{column}'
            f'<animateTransform attributeName="transform" type="translate" from="0 0" to="0 -{steps * line}" '
            f'dur="{1.6 + i * 0.25:.2f}s" begin="{delay + i * 0.08:.2f}s" fill="freeze" calcMode="spline" '
            f'keySplines=".15 .75 .2 1" keyTimes="0;1"/></g></svg>')
    return "".join(out)


def render_stats(user):
    repos = user["repositories"]
    cal = user["contributionsCollection"]["contributionCalendar"]
    weeks = cal["weeks"]
    days = [(d["date"], d["contributionCount"]) for w in weeks for d in w["contributionDays"]]
    active = sum(1 for _, c in days if c)
    peak = max((c for _, c in days), default=0) or 1
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
    n_langs = len({r["primaryLanguage"]["name"] for r in repos["nodes"] if r["primaryLanguage"]})

    W, PAD = 840, 28
    inner = W - 2 * PAD
    out = []
    add = out.append

    # --- stat tiles -------------------------------------------------------
    tiles = [
        (repos["totalCount"], "public repositories"),
        (cal["totalContributions"], "contributions, last 12 months"),
        (active, "active days, last 12 months"),
        (n_langs, "languages in use"),
    ]
    gap = 12
    tw = (inner - gap * (len(tiles) - 1)) / len(tiles)
    for i, (value, label) in enumerate(tiles):
        x = PAD + i * (tw + gap)
        add(f'<g class="fade" style="animation-delay:{i * 120}ms">'
            f'<rect x="{x:.1f}" y="56" width="{tw:.1f}" height="78" rx="10" fill="{TILE}" stroke="{BORDER}"/>'
            f'{odometer(value, x + 16, 66, 0.2 + i * 0.12)}'
            f'<text x="{x + 16:.1f}" y="118" font-size="11.5" fill="{TEXT2}">{escape(label)}</text></g>')

    # --- repos by primary language ----------------------------------------
    add(f'<text x="{PAD}" y="170" font-size="12" font-weight="600" fill="{TEXT2}" letter-spacing=".6">'
        f'REPOSITORIES BY PRIMARY LANGUAGE</text>')
    add(f'<clipPath id="bar"><rect x="{PAD}" y="182" width="0" height="12" rx="4">'
        f'<animate attributeName="width" from="0" to="{inner}" dur="1.4s" begin="0.4s" fill="freeze" '
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

    # --- isometric contribution skyline -------------------------------------
    add(f'<text x="{PAD}" y="262" font-size="12" font-weight="600" fill="{TEXT2}" letter-spacing=".6">'
        f'CONTRIBUTION SKYLINE, LAST 12 MONTHS</text>')
    lx = W - PAD - 5 * 14 - 74
    add(f'<text x="{lx}" y="262" font-size="10.5" fill="{MUTED}">Less</text>')
    for i, color in enumerate(HEAT):
        add(f'<rect x="{lx + 30 + i * 14}" y="252.5" width="11" height="11" rx="2.5" fill="{color}"/>')
    add(f'<text x="{lx + 34 + 5 * 14}" y="262" font-size="10.5" fill="{MUTED}">More</text>')

    a, b, max_h, inset = 13.0, 3.6, 46.0, 0.09
    ox, oy = PAD + 7 * a + 4, 262 + 26 + max_h

    def P(w, d, h=0.0):
        return ox + (w - d) * a, oy + (w + d) * b - h

    def pts(*points):
        return " ".join(f"{px:.1f},{py:.1f}" for px, py in points)

    last_month = None
    labels = []
    for wi, week in enumerate(weeks):
        first = dt.date.fromisoformat(week["contributionDays"][0]["date"])
        if first.month != last_month:
            if last_month is not None:
                px, py = P(wi, 7)
                labels.append(f'<text x="{px - 4:.1f}" y="{py + 15:.1f}" font-size="10.5" fill="{MUTED}">'
                              f'{first.strftime("%b")}</text>')
            last_month = first.month
        add(f'<g class="rise" style="animation-delay:{700 + wi * 28}ms">')
        for d in week["contributionDays"]:
            row = (dt.date.fromisoformat(d["date"]).weekday() + 1) % 7  # Sunday at the back
            c = d["contributionCount"]
            lv = level(c)
            h = 2.5 if c == 0 else 7 + (max_h - 7) * math.sqrt(c / peak)
            top = HEAT[lv]
            w0, w1, d0, d1 = wi + inset, wi + 1 - inset, row + inset, row + 1 - inset
            add(f'<g><title>{d["date"]}: {c}</title>'
                f'<polygon points="{pts(P(w0, d1, h), P(w1, d1, h), P(w1, d1), P(w0, d1))}" fill="{shade(top, .72)}"/>'
                f'<polygon points="{pts(P(w1, d0, h), P(w1, d1, h), P(w1, d1), P(w1, d0))}" fill="{shade(top, .5)}"/>'
                f'<polygon points="{pts(P(w0, d0, h), P(w1, d0, h), P(w1, d1, h), P(w0, d1, h))}" fill="{top}"/></g>')
        add('</g>')
    out.extend(labels)

    H = round(P(len(weeks), 7)[1] + 34)
    today = dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y")
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'font-family="{FONT}" role="img" aria-label="GitHub activity for {escape(LOGIN)}: '
        f'{repos["totalCount"]} public repositories, {cal["totalContributions"]} contributions in the last 12 months">'
        '<style>'
        '.fade{opacity:0;animation:fade .6s ease-out forwards}'
        '.rise{opacity:0;animation:rise .7s cubic-bezier(.2,.8,.2,1) forwards}'
        '.live{animation:pulse 2s ease-in-out infinite}'
        '@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}'
        '@keyframes rise{from{opacity:0;transform:translateY(34px)}to{opacity:1;transform:none}}'
        '@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}'
        '@media (prefers-reduced-motion:reduce){.fade,.rise{animation:none;opacity:1}.live{animation:none}}'
        '</style>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="{SURFACE}" stroke="{BORDER}"/>'
        f'<circle class="live" cx="{PAD + 4}" cy="31" r="4" fill="{GREEN}"/>'
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


# ---------------------------------------------------------------------- maze

COLS, ROWS, CELL = 30, 10, 24


def clean_seed(raw):
    raw = re.sub(r"^\s*maze\s*:?", "", raw or "", flags=re.I)
    seed = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")[:24].strip("-")
    return seed or "mystery"


def clean_login(raw):
    m = re.match(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", raw or "")
    return m.group(0) if m else None


def build_maze(seed):
    """Depth-first maze with a few extra openings, so there is more than one route."""
    rng = random.Random(f"maze:{seed}")
    open_edges = set()

    def link(p, q):
        open_edges.add((p, q))
        open_edges.add((q, p))

    def neighbours(cell):
        r, c = cell
        return [(r + dr, c + dc) for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0))
                if 0 <= r + dr < ROWS and 0 <= c + dc < COLS]

    start_cell = (rng.randrange(ROWS), rng.randrange(COLS))
    seen, stack = {start_cell}, [start_cell]
    while stack:
        options = [n for n in neighbours(stack[-1]) if n not in seen]
        if not options:
            stack.pop()
            continue
        nxt = rng.choice(options)
        link(stack[-1], nxt)
        seen.add(nxt)
        stack.append(nxt)
    for _ in range(COLS * ROWS // 7):
        cell = (rng.randrange(ROWS), rng.randrange(COLS))
        link(cell, rng.choice(neighbours(cell)))

    start = (rng.randrange(ROWS), 0)
    goal = (rng.randrange(ROWS), COLS - 1)
    return open_edges, neighbours, start, goal


def solve(open_edges, neighbours, start, goal):
    """A* with a Manhattan heuristic. Returns (cells in the order expanded, shortest path)."""
    def h(cell):
        return abs(cell[0] - goal[0]) + abs(cell[1] - goal[1])

    best = {start: 0}
    parent = {}
    heap = [(h(start), 0, start)]
    order, done, tick = [], set(), 0
    while heap:
        _, _, cell = heapq.heappop(heap)
        if cell in done:
            continue
        done.add(cell)
        order.append(cell)
        if cell == goal:
            break
        for n in neighbours(cell):
            if (cell, n) not in open_edges:
                continue
            g = best[cell] + 1
            if g < best.get(n, 1 << 30):
                best[n] = g
                parent[n] = cell
                tick += 1
                heapq.heappush(heap, (g + h(n), tick, n))
    path = [goal]
    while path[-1] != start:
        path.append(parent[path[-1]])
    return order, path[::-1]


def render_maze(seed, by, date_label):
    open_edges, neighbours, start, goal = build_maze(seed)
    order, path = solve(open_edges, neighbours, start, goal)
    W = 840
    ox, oy = (W - COLS * CELL) / 2, 62
    H = oy + ROWS * CELL + 46
    DUR = 14

    def centre(cell):
        return ox + cell[1] * CELL + CELL / 2, oy + cell[0] * CELL + CELL / 2

    out = []
    add = out.append

    # explored cells light up in the order A* expanded them
    buckets = min(70, len(order))
    for i in range(buckets):
        chunk = order[len(order) * i // buckets: len(order) * (i + 1) // buckets]
        t = 0.05 + 0.5 * i / buckets
        rects = "".join(
            f'<rect x="{ox + c * CELL + 2.5:.1f}" y="{oy + r * CELL + 2.5:.1f}" width="{CELL - 5}" '
            f'height="{CELL - 5}" rx="4"/>' for r, c in chunk)
        add(f'<g fill="#1c5cab" opacity="0">{rects}<animate attributeName="opacity" '
            f'values="0;0;.95;.42;.42;0" keyTimes="0;{t:.4f};{t + 0.008:.4f};{t + 0.05:.4f};0.95;1" '
            f'dur="{DUR}s" repeatCount="indefinite"/></g>')

    # walls
    d = [f"M{ox} {oy}h{COLS * CELL}v{ROWS * CELL}h-{COLS * CELL}z"]
    for r in range(ROWS):
        for c in range(COLS):
            if c + 1 < COLS and ((r, c), (r, c + 1)) not in open_edges:
                d.append(f"M{ox + (c + 1) * CELL} {oy + r * CELL}v{CELL}")
            if r + 1 < ROWS and ((r, c), (r + 1, c)) not in open_edges:
                d.append(f"M{ox + c * CELL} {oy + (r + 1) * CELL}h{CELL}")
    add(f'<path d="{"".join(d)}" fill="none" stroke="#55555b" stroke-width="1.5" stroke-linecap="round"/>')

    # shortest path, drawn after the search reaches the goal
    line = "M" + "L".join(f"{x:.0f} {y:.0f}" for x, y in map(centre, path))
    length = (len(path) - 1) * CELL
    add(f'<path d="{line}" fill="none" stroke="#86b6ef" stroke-width="3.5" stroke-linecap="round" '
        f'stroke-linejoin="round" stroke-dasharray="{length}" stroke-dashoffset="{length}">'
        f'<animate attributeName="stroke-dashoffset" values="{length};{length};0;0" keyTimes="0;0.58;0.84;1" '
        f'dur="{DUR}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="1;1;0" keyTimes="0;0.95;1" dur="{DUR}s" repeatCount="indefinite"/></path>')
    sx, sy = centre(start)
    gx, gy = centre(goal)
    add(f'<circle r="5.5" fill="{TEXT}"><animateMotion path="{line}" keyPoints="0;0;1;1" keyTimes="0;0.58;0.84;1" '
        f'calcMode="linear" dur="{DUR}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes="0;0.57;0.58;0.84;0.86;1" dur="{DUR}s" '
        f'repeatCount="indefinite"/></circle>')
    add(f'<circle cx="{sx}" cy="{sy}" r="6" fill="{BLUE}"/>')
    add(f'<circle cx="{gx}" cy="{gy}" r="6" fill="{SURFACE}" stroke="#8b8b8d" stroke-width="2">'
        f'<animate attributeName="fill" values="{SURFACE};{SURFACE};{GREEN};{GREEN};{SURFACE}" '
        f'keyTimes="0;0.84;0.85;0.95;1" dur="{DUR}s" repeatCount="indefinite"/>'
        f'<animate attributeName="stroke" values="#8b8b8d;#8b8b8d;{GREEN};{GREEN};#8b8b8d" '
        f'keyTimes="0;0.84;0.85;0.95;1" dur="{DUR}s" repeatCount="indefinite"/></circle>')
    add(f'<circle cx="{gx}" cy="{gy}" r="6" fill="none" stroke="{GREEN}" stroke-width="2" opacity="0">'
        f'<animate attributeName="r" values="6;6;24;24" keyTimes="0;0.84;0.93;1" dur="{DUR}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="0;0;.9;0;0" keyTimes="0;0.84;0.85;0.93;1" dur="{DUR}s" '
        f'repeatCount="indefinite"/></circle>')
    add(f'<text x="{ox - 10}" y="{sy + 4}" font-size="11" fill="{MUTED}" text-anchor="end" font-family="{MONO}">in</text>')
    add(f'<text x="{ox + COLS * CELL + 10}" y="{gy + 4}" font-size="11" fill="{MUTED}" font-family="{MONO}">out</text>')

    credit = f"set by @{by}" if by else "daily maze"
    foot_y = oy + ROWS * CELL + 28
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'font-family="{FONT}" role="img" aria-label="A maze generated from the seed {escape(seed)}, solved by '
        f'A-star search: {len(order)} cells explored, shortest path {len(path) - 1} steps">'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="{SURFACE}" stroke="{BORDER}"/>'
        f'<circle cx="32" cy="31" r="4" fill="{BLUE}"><animate attributeName="opacity" values="1;.25;1" dur="2s" '
        f'repeatCount="indefinite"/></circle>'
        f'<text x="44" y="35" font-size="12" font-weight="600" fill="{TEXT2}" letter-spacing=".6">A* SEARCH, SOLVING '
        f'<tspan fill="{TEXT}" font-family="{MONO}" letter-spacing="0">"{escape(seed)}"</tspan></text>'
        f'<text x="{W - 28}" y="35" font-size="11.5" fill="{MUTED}" text-anchor="end">{escape(credit)} · {escape(date_label)}</text>'
        f'<text x="{ox}" y="{foot_y}" font-size="12" fill="{TEXT2}">explored <tspan fill="{TEXT}" font-weight="700">'
        f'{len(order)}</tspan> of {COLS * ROWS} cells</text>'
        f'<text x="{W / 2}" y="{foot_y}" font-size="12" fill="{TEXT2}" text-anchor="middle">shortest path '
        f'<tspan fill="{TEXT}" font-weight="700">{len(path) - 1}</tspan> steps</text>'
        f'<text x="{ox + COLS * CELL}" y="{foot_y}" font-size="12" fill="{MUTED}" text-anchor="end">'
        f'your word, your maze — link below</text>'
    )
    return head + "".join(out) + "</svg>\n", len(order), len(path) - 1


def update_maze():
    """Decide which maze to show, render it, and return the README block."""
    state_file = ROOT / "data" / "maze.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    today = dt.datetime.now(dt.timezone.utc).date()
    title = os.environ.get("MAZE_TITLE")
    if title is not None:
        by = clean_login(os.environ.get("MAZE_BY"))
        state.update(seed=clean_seed(title), by=by, date=today.isoformat())
        if by:
            hall = [e for e in state.get("hall", []) if e["by"] != by]
            state["hall"] = ([{"by": by, "seed": state["seed"]}] + hall)[:8]
    elif state.get("date") != today.isoformat() or "seed" not in state:
        state.update(seed=f"daily-{today.isoformat()}", by=None, date=today.isoformat())

    svg, explored, steps = render_maze(state["seed"], state.get("by"), today.strftime("%d %b %Y"))
    (ROOT / "assets" / "maze.svg").write_text(svg, encoding="utf-8")
    state_file.parent.mkdir(exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    who = f"set by [@{state['by']}](https://github.com/{state['by']})" if state.get("by") else "today's daily maze"
    block = (f"**Now solving:** `{state['seed']}` — {who} · A\\* explored **{explored}** of {COLS * ROWS} cells · "
             f"shortest path **{steps}** steps")
    if state.get("hall"):
        names = " · ".join(f"[@{e['by']}](https://github.com/{e['by']}) `{e['seed']}`" for e in state["hall"])
        block += f"\n\n<sub>Recent challengers: {names}</sub>"
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"seed={state['seed']}\nexplored={explored}\nsteps={steps}\n")
    return block


# ------------------------------------------------------------------- toolbox

def render_toolbox():
    W, H, row_h, chip_h, gap = 840, 148, 40, 28, 12
    out = []
    for i, names in enumerate(TOOLBOX):
        chips, x = [], 0.0
        for name in names:
            w = len(name) * 8.1 + 30
            chips.append((x, w, name))
            x += w + gap
        span = x
        copies = math.ceil(W / span) + 1
        y = 16 + i * row_h
        body = []
        for k in range(copies):
            for cx, w, name in chips:
                px = cx + k * span
                body.append(
                    f'<rect x="{px:.1f}" y="{y}" width="{w:.1f}" height="{chip_h}" rx="14" fill="{TILE}" stroke="#3a3a3e"/>'
                    f'<circle cx="{px + 14:.1f}" cy="{y + chip_h / 2}" r="3" fill="{BLUE}"/>'
                    f'<text x="{px + 24:.1f}" y="{y + 18.5}">{escape(name)}</text>')
        frm, to = (0, -span) if i % 2 == 0 else (-span, 0)
        out.append(
            f'<g>{"".join(body)}<animateTransform attributeName="transform" type="translate" '
            f'from="{frm:.1f} 0" to="{to:.1f} 0" dur="{span / 26:.1f}s" repeatCount="indefinite"/></g>')
    label = "Toolbox: " + "; ".join(", ".join(row) for row in TOOLBOX)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'font-family="{MONO}" font-size="13" fill="{TEXT}" role="img" aria-label="{escape(label)}">'
        f'<defs><linearGradient id="l" x1="0" x2="1"><stop offset="0" stop-color="{SURFACE}"/>'
        f'<stop offset="1" stop-color="{SURFACE}" stop-opacity="0"/></linearGradient>'
        f'<linearGradient id="r" x1="1" x2="0"><stop offset="0" stop-color="{SURFACE}"/>'
        f'<stop offset="1" stop-color="{SURFACE}" stop-opacity="0"/></linearGradient>'
        f'<clipPath id="c"><rect width="{W}" height="{H}" rx="12"/></clipPath></defs>'
        f'<g clip-path="url(#c)"><rect width="{W}" height="{H}" fill="{SURFACE}"/>{"".join(out)}'
        f'<rect width="110" height="{H}" fill="url(#l)"/><rect x="{W - 110}" width="110" height="{H}" fill="url(#r)"/></g>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="none" stroke="{BORDER}"/></svg>\n')


# ---------------------------------------------------------------------- main

def replace_block(text, name, body):
    block = f"<!--{name}:START-->\n{body}\n<!--{name}:END-->"
    new, n = re.subn(rf"<!--{name}:START-->.*?<!--{name}:END-->", lambda _: block, text, flags=re.S)
    if not n:
        print(f"warning: {name} markers not found in README.md", file=sys.stderr)
    return new


def main():
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")

    text = replace_block(text, "MAZE", update_maze())
    (assets / "toolbox.svg").write_text(render_toolbox(), encoding="utf-8")

    # A visitor's maze must not depend on the stats API being reachable.
    if os.environ.get("MAZE_TITLE") is None:
        user = fetch()
        (assets / "stats.svg").write_text(render_stats(user), encoding="utf-8")
        text = replace_block(text, "RECENT", render_recent(user))

    readme.write_text(text, encoding="utf-8")
    print("profile assets updated")


if __name__ == "__main__":
    main()
