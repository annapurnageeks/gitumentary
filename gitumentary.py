#!/usr/bin/env python3
"""
gitumentary: turn any git repository's history into a short animated documentary.

Usage:
    python3 gitumentary.py PATH_TO_REPO                       # writes documentary.html
    python3 gitumentary.py PATH_TO_REPO --open                # ...and opens it in your browser
    python3 gitumentary.py PATH_TO_REPO --brief               # prints the facts an AI narrator needs
    python3 gitumentary.py PATH_TO_REPO --script script.json  # uses your own titles and narration

How it works, in four steps:
    1. read_history()  asks git for every commit and how many lines it changed in each file
    2. replay()        walks through the commits in order, tracking how big each folder is
    3. chapters        cuts the history into a few chapters and collects facts about each one
    4. render()        puts everything into player.html, which animates it in the browser

Only the Python standard library is used, so there is nothing to install.
"""

import argparse
import bisect
import json
import re
import subprocess
import sys
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Change this to your own repository after you publish it. It appears in the end credits.
PROJECT_URL = "https://github.com/annapurnageeks/gitumentary"

FRAMES_PER_CHAPTER = 40  # how many snapshots of the codebase the animation gets per chapter
MAX_AREAS = 40           # the biggest folders get their own box; the rest are merged into "other"
CREDITS = 40             # people named in the end credits (by number of commits); the rest are "and N more"

# Generated or vendored files. Counting them would make the picture lie.
NOISE_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "Cargo.lock", "poetry.lock",
    "Pipfile.lock", "uv.lock", "go.sum", "composer.lock", "Gemfile.lock", "flake.lock",
}
NOISE_DIRS = {"node_modules", "vendor", "dist", "build", ".next", "__pycache__", "third_party", "target"}
NOISE_SUFFIXES = (".min.js", ".min.css", ".map", ".snap", ".lock")

# File extension -> (language, color). Colors follow GitHub's, lightened where too dark for a dark screen.
LANGUAGES = {}
for _exts, _lang in [
    ("py pyi", ("Python", "#3572A5")), ("ipynb", ("Jupyter", "#DA5B0B")),
    ("js mjs cjs jsx", ("JavaScript", "#f1e05a")), ("ts tsx mts cts", ("TypeScript", "#3178c6")),
    ("go", ("Go", "#00ADD8")), ("rs", ("Rust", "#dea584")), ("java", ("Java", "#b07219")),
    ("kt kts", ("Kotlin", "#A97BFF")), ("swift", ("Swift", "#F05138")), ("c h", ("C", "#a8b9cc")),
    ("cc cpp cxx hpp hh", ("C++", "#f34b7d")), ("cs", ("C#", "#2fa84f")), ("rb", ("Ruby", "#cc342d")),
    ("php", ("PHP", "#7a86c2")), ("html htm", ("HTML", "#e34c26")), ("css scss sass less", ("CSS", "#8e6bd6")),
    ("vue", ("Vue", "#41b883")), ("svelte", ("Svelte", "#ff3e00")), ("dart", ("Dart", "#00B4AB")),
    ("lua", ("Lua", "#6c7fd8")), ("zig", ("Zig", "#ec915c")), ("ex exs", ("Elixir", "#9b6bb5")),
    ("hs", ("Haskell", "#8f7fd1")), ("scala", ("Scala", "#c22d40")), ("sql", ("SQL", "#e38c00")),
    ("sh bash zsh fish", ("Shell", "#89e051")), ("md mdx rst txt adoc", ("Docs", "#b3a68c")),
    ("json yml yaml toml ini cfg xml", ("Config", "#6b7480")),
]:
    for _ext in _exts.split():
        LANGUAGES["." + _ext] = _lang
UNKNOWN_LANGUAGE = ("Other", "#565c66")

# Commit messages that often mark a turning point in a project's story.
NOTABLE = re.compile(
    r"\b(initial|first|launch|release[ds]?|v\d+(\.\d+)+|rewr[io]te|refactor\w*|migrat\w*|port(ed)? to|"
    r"introduc\w*|remove[sd]?|drop(ped|s)?|deprecat\w*|breaking|replace[sd]?)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------------------------
# 1. Reading the history
# ---------------------------------------------------------------------------------------------

def git(repo, *args):
    """Run a git command inside the repo and return what it printed."""
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        sys.exit(f"gitumentary: `git {' '.join(args)}` failed\n{result.stderr.strip()}")
    return result.stdout


def is_noise(path):
    parts = path.split("/")
    return parts[-1] in NOISE_FILES or path.endswith(NOISE_SUFFIXES) or any(p in NOISE_DIRS for p in parts[:-1])


def read_history(repo, keep_everything=False):
    """Return every commit, oldest first. Each one lists (path, lines added, lines deleted) per file.

    --no-renames makes git report a moved file as "deleted here, added there", which keeps
    our line counting simple. --no-merges skips merge commits, which repeat other commits' work.
    """
    command = ["git", "-C", str(repo), "-c", "core.quotepath=off", "log", "--reverse", "--no-merges",
               "--no-renames", "--numstat", "--format=%x1e%h%x1f%ct%x1f%aN%x1f%s"]
    commits = []
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          encoding="utf-8", errors="replace") as process:
        for line in process.stdout:
            line = line.rstrip("\n")
            if line.startswith("\x1e"):  # a new commit starts: hash, time, author, message
                short_hash, timestamp, author, subject = line[1:].split("\x1f", 3)
                commits.append({"hash": short_hash, "time": int(timestamp), "author": author,
                                "subject": subject, "files": []})
            elif line and commits:       # one changed file: "added<TAB>deleted<TAB>path"
                added, deleted, path = line.split("\t", 2)
                if added == "-":         # a binary file; git can't count its lines
                    continue
                if keep_everything or not is_noise(path):
                    commits[-1]["files"].append((path, int(added), int(deleted)))
        error = process.stderr.read()
    if process.returncode != 0:
        sys.exit(f"gitumentary: could not read the history of {repo}\n{error.strip()}")
    steady_times(commits)
    return commits


def steady_times(commits, reach=12):
    """Make commit times move forward only, without letting a few odd timestamps wreck the timeline.

    Timestamps can be out of order: rebases, wrong clocks, or a whole repository imported with
    rewritten dates. Simply forcing time forward would let one commit dated 2024 drag every
    commit after it to 2024.

    So a commit is treated as an outlier when it is out of order by more than 30 days: later
    than the typical time of the commits that come after it, or earlier than the typical time
    of the commits that came before it. Commits on the edge of a real pause are in order, so
    real pauses are kept. An outlier takes the typical time of its neighbours; then time is
    forced to move forward."""
    times = [c["time"] for c in commits]
    month = 30 * 86400

    def median(values):
        return sorted(values)[len(values) // 2]

    latest = 0
    for i, commit in enumerate(commits):
        before, after = times[max(0, i - reach):i], times[i + 1:i + 1 + reach]
        own = times[i]
        too_late = after and own > median(after) + month
        too_early = before and own < median(before) - month
        if too_late or too_early:
            own = median(before + after)
        latest = max(latest, own)
        commit["time"] = latest


def read_tag_times(repo):
    out = git(repo, "for-each-ref", "--format=%(creatordate:unix)", "refs/tags")
    return sorted(int(t) for t in out.split() if t.isdigit())


# ---------------------------------------------------------------------------------------------
# 2. Replaying the history
# ---------------------------------------------------------------------------------------------

def area_of(path):
    """Files are grouped into 'areas': the first two folders of their path."""
    folders = path.split("/")[:-1]
    return "/".join(folders[:2]) if folders else "(root)"


def language_of(path):
    return LANGUAGES.get(Path(path).suffix.lower(), UNKNOWN_LANGUAGE)


def replay(commits):
    """Walk through the commits in order and work out how much each area grew or shrank.

    Git only tells us lines added and deleted, so we keep a running line count for every file.
    When a file's count reaches zero it has been deleted (or moved somewhere else).
    Returns the main language of each area.
    """
    lines_in_file = {}
    total = 0
    language_lines = defaultdict(Counter)  # area -> language -> lines ever added
    for commit in commits:
        growth = defaultdict(int)
        for path, added, deleted in commit["files"]:
            area = area_of(path)
            before = lines_in_file.get(path, 0)
            after = max(0, before + added - deleted)
            if after:
                lines_in_file[path] = after
            else:
                lines_in_file.pop(path, None)
            growth[area] += after - before
            language = language_of(path)
            # Docs and config count for less, so a code folder full of test snapshots still reads as code.
            language_lines[area][language] += added * (0.3 if language[0] in ("Docs", "Config") else 1)
        total += sum(growth.values())
        commit["growth"] = dict(growth)
        commit["areas"] = set(growth)
        commit["added"] = sum(f[1] for f in commit["files"])
        commit["deleted"] = sum(f[2] for f in commit["files"])
        commit["total"] = total  # lines in the whole codebase after this commit
    return {area: counts.most_common(1)[0][0] for area, counts in language_lines.items() if counts}


def pick_areas(commits):
    """The areas that get their own box, biggest first (by the largest size they ever reached)."""
    size, peak = Counter(), Counter()
    for commit in commits:
        for area, change in commit["growth"].items():
            size[area] += change
            peak[area] = max(peak[area], size[area])
    return [area for area, biggest in peak.most_common(MAX_AREAS) if biggest > 0]


# ---------------------------------------------------------------------------------------------
# 3. Chapters, facts and plot twists
# ---------------------------------------------------------------------------------------------

def find_chapters(commits, tag_times):
    """Cut the history into chapters of roughly equal size, nudged toward release tags or
    long pauses so that each cut lands on a natural turning point.
    Returns (start, end) commit positions; end is not included."""
    n = len(commits)
    k = min(3, n) if n < 40 else 4 if n < 300 else 5 if n < 3000 else 6
    times = [c["time"] for c in commits]
    tag_positions = sorted({bisect.bisect_left(times, t) for t in tag_times} - {0, n})
    reach = max(1, n // (2 * k))
    cuts = [0]
    for j in range(1, k):
        ideal = round(j * n / k)
        low, high = max(cuts[-1] + 1, ideal - reach), min(n - 1, ideal + reach)
        if low > high:
            continue
        tags_nearby = [p for p in tag_positions if low <= p <= high]
        if tags_nearby:
            cut = min(tags_nearby, key=lambda p: abs(p - ideal))
        else:  # no release nearby: cut at the longest pause instead
            cut = max(range(low, high + 1), key=lambda i: times[i] - times[i - 1])
        cuts.append(cut)
    cuts.append(n)
    return list(zip(cuts, cuts[1:]))


def day(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")


def long_date(timestamp):
    d = datetime.fromtimestamp(timestamp, timezone.utc)
    return f"{d:%B} {d.day}, {d.year}"


def span(seconds):
    days = seconds / 86400
    if days < 1.5:
        return "a single day"
    if days < 14:
        return f"{round(days)} days"
    if days < 60:
        return f"{round(days / 7)} weeks"
    if days < 700:
        return f"{round(days / 30.44)} months"
    years = days / 365.25
    return f"{round(years)} years" if years >= 3 or round(years, 1) == round(years) else f"{years:.1f} years"


def number(n):
    return f"{n:,}"


def plural(n, word):
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def commit_card(c):
    return {"hash": c["hash"], "date": day(c["time"]), "author": c["author"], "subject": c["subject"],
            "added": c["added"], "deleted": c["deleted"]}


def describe_chapter(commits, start, end, seen):
    """Collect the facts about one chapter. `seen` remembers the people and areas from earlier chapters."""
    chunk = commits[start:end]
    people = Counter(c["author"] for c in chunk)
    newcomers = [p for p in dict.fromkeys(c["author"] for c in chunk) if p not in seen["people"]]
    seen["people"].update(newcomers)

    new_areas = []
    for c in chunk:
        for area, change in c["growth"].items():
            seen["size"][area] += change
            if seen["size"][area] > 0 and area not in seen["areas"]:
                seen["areas"].add(area)
                new_areas.append(area)

    pauses = [chunk[i]["time"] - chunk[i - 1]["time"] for i in range(1, len(chunk))]
    step = max(1, len(chunk) // 8)
    return {
        "start": start, "end": end,
        "first_time": chunk[0]["time"], "last_time": chunk[-1]["time"],
        "commits": len(chunk),
        "people_count": len(people),
        "people": people.most_common(6),
        "newcomers": newcomers,
        "added": sum(c["added"] for c in chunk),
        "deleted": sum(c["deleted"] for c in chunk),
        "size_before": commits[start - 1]["total"] if start else 0,
        "size_after": chunk[-1]["total"],
        "busiest_areas": Counter(a for c in chunk for a in c["areas"]).most_common(4),
        "new_areas": new_areas[:6],
        "first_commit": commit_card(chunk[0]),
        "biggest_commit": commit_card(max(chunk, key=lambda c: c["added"] + c["deleted"])),
        "notable_commits": [commit_card(c) for c in chunk if NOTABLE.search(c["subject"])][:6],
        "sample_commits": [commit_card(c) for c in chunk[::step]][:8],
        "longest_pause_days": round(max(pauses) / 86400) if pauses else 0,
        "fix_share": round(100 * sum("fix" in c["subject"].lower() for c in chunk) / len(chunk)),
        "reverts": sum(c["subject"].lower().startswith("revert") for c in chunk),
    }


def find_twists(commits):
    """Moments worth an on-screen card. Returns (commit position, kind, text), most important first."""
    twists = []
    n = len(commits)

    # The biggest cleanup: the most lines removed by a single commit.
    i = max(range(n), key=lambda i: commits[i]["deleted"] - commits[i]["added"])
    removed = commits[i]["deleted"] - commits[i]["added"]
    before = commits[i - 1]["total"] if i else 0
    if removed >= 300 and removed >= 0.05 * before:
        twists.append((i, "Plot twist", f"{number(removed)} lines deleted in one commit"))

    # The longest silence between two commits.
    if n > 1:
        i = max(range(1, n), key=lambda i: commits[i]["time"] - commits[i - 1]["time"])
        days = (commits[i]["time"] - commits[i - 1]["time"]) // 86400
        if days >= 45:
            twists.append((i, "Silence", f"{number(days)} days without a single commit"))

    # Milestones: the codebase and the cast reaching a new order of magnitude.
    for threshold in (10_000, 100_000, 1_000_000):
        first_size = commits[0]["total"]
        hit = next((i for i, c in enumerate(commits) if c["total"] >= threshold), None)
        if hit is not None and first_size < threshold:
            twists.append((hit, "Milestone", f"{number(threshold)} lines of code"))
    people = set()
    for i, c in enumerate(commits):
        if c["author"] not in people:
            people.add(c["author"])
            if len(people) in (10, 100, 1000):
                twists.append((i, "Milestone", f"{number(len(people))} contributors"))
    return twists


def default_story(facts, total_people):
    """Write plain, factual narration. An AI narrator (see SKILL.md) can replace it with a better one."""
    chapters, used_titles = [], set()
    for i, f in enumerate(facts):
        who = f["people"][0][0] if f["people_count"] == 1 else f"{number(f['people_count'])} people"
        how_long = span(f["last_time"] - f["first_time"])
        areas = [a for a, _ in f["busiest_areas"] if a != "(root)"]
        is_last = i == len(facts) - 1

        if i == 0:
            first = f["first_commit"]
            title = "The Beginning"
            quote = first["subject"].rstrip()
            text = f"It began on {long_date(f['first_time'])}, when {first['author']} made the first commit: “{quote}”"
            text += "" if quote[-1:] in ".!?" else "."
            if f["commits"] > 1:
                text += f" Over the next {how_long}, {who} made {number(f['commits'])} commits"
                text += f", most of them in {areas[0]}." if areas else "."
        else:
            title = "Where It Stands" if is_last else next(
                (f"The {a} Era" for a in areas if f"The {a} Era" not in used_titles), f"Chapter {i + 1}")
            text = f"Over {how_long}, {who} made {number(f['commits'])} commits"
            text += f", most of them in {areas[0]}." if areas else "."
            if len(f["newcomers"]) == 1:
                text += f" {f['newcomers'][0]} joined the cast."
            elif f["newcomers"]:
                text += f" {number(len(f['newcomers']))} new people joined, starting with {f['newcomers'][0]}."
        growth = f["size_after"] - f["size_before"]
        if is_last:
            text += f" Today the codebase holds {number(f['size_after'])} lines, written by {number(total_people)} {'person' if total_people == 1 else 'people'}."
        elif growth > 0:
            text += f" The codebase grew to {number(f['size_after'])} lines."
        elif growth < 0:
            text += f" The codebase shrank by {number(-growth)} lines."
        used_titles.add(title)
        chapters.append({"title": title, "narration": text})
    return chapters


# ---------------------------------------------------------------------------------------------
# 4. Animation frames, the brief, and rendering
# ---------------------------------------------------------------------------------------------

def hottest(touched):
    """The areas that saw the most work since the last frame, as [area, glow from 0 to 1].
    Only these light up, so the eye goes where the action is."""
    if not touched:
        return []
    top = max(touched.values())
    return [[area, round(count / top, 2)] for area, count in touched.most_common(6) if count >= top / 4]


def build_frames(commits, chapter_ranges, areas):
    """Snapshots of every area's size, spread evenly through each chapter.
    Frame 0 of a chapter is the state just before its first commit, so each chapter grows from
    where the last one ended. Position -1 means 'before the first commit'."""
    slot = {area: i for i, area in enumerate(areas)}
    other = len(areas)
    plans = []
    for start, end in chapter_ranges:
        count = min(FRAMES_PER_CHAPTER, end - start + 1)
        plans.append([start - 1 + round((end - start) * k / (count - 1)) for k in range(count)])
    wanted = {i for plan in plans for i in plan}

    sizes = [0] * (len(areas) + 1)
    people, touched = set(), Counter()
    snapshots = {-1: {"t": commits[0]["time"], "s": list(sizes), "c": 0, "a": 0, "l": 0, "x": [],
                      "h": "", "w": "", "m": ""}}
    for i, c in enumerate(commits):
        for area, change in c["growth"].items():
            sizes[slot.get(area, other)] += change
        touched.update(slot.get(area, other) for area in c["areas"])  # how often each area was touched
        people.add(c["author"])
        if i in wanted:
            snapshots[i] = {"t": c["time"], "s": [max(0, v) for v in sizes], "c": i + 1, "a": len(people),
                            "l": max(0, sum(sizes)), "x": hottest(touched),
                            "h": c["hash"], "w": c["author"], "m": c["subject"][:140]}
            touched = Counter()
    frames = []
    for plan in plans:
        chapter_frames = [dict(snapshots[i]) for i in plan]
        chapter_frames[0]["x"] = []
        frames.append(chapter_frames)
    return frames


def build_story(repo, title, keep_everything):
    commits = read_history(repo, keep_everything)
    if not commits:
        sys.exit("gitumentary: this repository has no commits yet. Every story needs a first chapter!")
    area_language = replay(commits)
    areas = pick_areas(commits)
    chapter_ranges = find_chapters(commits, read_tag_times(repo))

    seen = {"people": set(), "areas": set(), "size": Counter()}
    facts = [describe_chapter(commits, start, end, seen) for start, end in chapter_ranges]
    cast = Counter(c["author"] for c in commits)
    first_seen = {}
    for c in commits:
        first_seen.setdefault(c["author"], c["time"])

    # Place each plot twist inside its chapter, at most two per chapter.
    for f in facts:
        f["twists"] = []
    for position, kind, text in find_twists(commits):
        for f in facts:
            if f["start"] <= position < f["end"] and len(f["twists"]) < 2:
                at = (position - f["start"] + 1) / (f["end"] - f["start"])
                f["twists"].append({"at": round(min(at, 0.85), 3), "kind": kind, "text": text,
                                    "hash": commits[position]["hash"]})

    frames = build_frames(commits, chapter_ranges, areas)
    script = default_story(facts, len(cast))
    story = {
        "title": title,
        "tagline": "a gitumentary",
        "repo": title,
        "first_time": commits[0]["time"],
        "last_time": commits[-1]["time"],
        "totals": {"commits": len(commits), "people": len(cast), "lines": commits[-1]["total"]},
        "peak_lines": max(frame["l"] for chapter in frames for frame in chapter) or 1,
        "areas": [{"name": a, "language": area_language.get(a, UNKNOWN_LANGUAGE)[0],
                   "color": area_language.get(a, UNKNOWN_LANGUAGE)[1]} for a in areas]
                 + [{"name": "other", "language": "Other", "color": UNKNOWN_LANGUAGE[1]}],
        "chapters": [
            {**script[i], "first_time": f["first_time"], "last_time": f["last_time"],
             "events": [{k: t[k] for k in ("at", "kind", "text")} for t in f["twists"]],
             "frames": frames[i]}
            for i, f in enumerate(facts)
        ],
        "cast": [{"name": name, "commits": count, "since": datetime.fromtimestamp(first_seen[name], timezone.utc).year}
                 for name, count in cast.most_common(CREDITS)],
        "project_url": PROJECT_URL,
    }
    return story, facts


def print_brief(story, facts):
    """Everything a narrator needs, as readable text (no animation data)."""
    t = story["totals"]
    print(f"# gitumentary brief: {story['repo']}\n")
    print(f"History: {day(story['first_time'])} -> {day(story['last_time'])} ({span(story['last_time'] - story['first_time'])}), "
          f"{number(t['commits'])} commits, {number(t['people'])} contributors, {number(t['lines'])} lines today.")
    print(f"Biggest areas: {', '.join(a['name'] + ' (' + a['language'] + ')' for a in story['areas'][:8])}")
    print(f"Chapters: {len(facts)}. Write exactly one title and narration per chapter, in this order.\n")
    for i, f in enumerate(facts):
        print(f"## Chapter {i + 1}: {day(f['first_time'])} -> {day(f['last_time'])} ({span(f['last_time'] - f['first_time'])})")
        print(f"commits: {number(f['commits'])} · people: {f['people_count']} · +{number(f['added'])} / -{number(f['deleted'])} lines "
              f"· size {number(f['size_before'])} -> {number(f['size_after'])}")
        print("top people: " + ", ".join(f"{p} ({n})" for p, n in f["people"]))
        if f["newcomers"]:
            more = f" (+{len(f['newcomers']) - 8} more)" if len(f["newcomers"]) > 8 else ""
            print("newcomers: " + ", ".join(f["newcomers"][:8]) + more)
        print("busiest areas: " + ", ".join(f"{a} ({n} commits)" for a, n in f["busiest_areas"]))
        if f["new_areas"]:
            print("new areas: " + ", ".join(f["new_areas"]))
        print(f"longest pause: {f['longest_pause_days']} days · fix commits: {f['fix_share']}% · reverts: {f['reverts']}")
        for label, c in [("first commit", f["first_commit"]), ("biggest commit", f["biggest_commit"])]:
            print(f"{label}: {c['hash']} {c['date']} {c['author']}: \"{c['subject']}\" (+{c['added']}/-{c['deleted']})")
        for c in f["notable_commits"]:
            print(f"notable: {c['hash']} {c['date']} {c['author']}: \"{c['subject']}\"")
        for c in f["sample_commits"]:
            print(f"sample: {c['hash']} {c['date']} {c['author']}: \"{c['subject']}\"")
        for twist in f["twists"]:
            print(f"on-screen card: [{twist['kind']}] {twist['text']} (commit {twist['hash']})")
        print(f"default title: {story['chapters'][i]['title']}")
        print(f"default narration: {story['chapters'][i]['narration']}\n")
    print("Write script.json like this, then run again with --script script.json:")
    skeleton = {"title": story["title"], "tagline": "a gitumentary",
                "chapters": [{"title": "...", "narration": "..."} for _ in facts]}
    print(json.dumps(skeleton, indent=2, ensure_ascii=False))


def apply_script(story, path):
    script = json.loads(Path(path).read_text(encoding="utf-8"))
    chapters = script.get("chapters", [])
    if len(chapters) != len(story["chapters"]):
        sys.exit(f"gitumentary: {path} has {len(chapters)} chapters, but this history has "
                 f"{len(story['chapters'])}. Run with --brief to see them.")
    for chapter, written in zip(story["chapters"], chapters):
        chapter["title"] = (written.get("title") or chapter["title"]).strip()
        chapter["narration"] = (written.get("narration") or chapter["narration"]).strip()
    story["title"] = (script.get("title") or story["title"]).strip()
    story["tagline"] = (script.get("tagline") or story["tagline"]).strip()


def render(story, output):
    template = (HERE / "player.html").read_text(encoding="utf-8")
    # "</" is escaped so that text in commit messages can never close the <script> tag early.
    data = json.dumps(story, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    Path(output).write_text(template.replace("__STORY_JSON__", data), encoding="utf-8")


def repo_name(repo):
    remote = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", remote)
    return match.group(1) if match else Path(repo).name


def main():
    # Windows may print with an old code page; never crash on an emoji or a contributor's name.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Turn a git repository's history into a short animated documentary.")
    parser.add_argument("repo", nargs="?", default=".", help="path to a git repository (default: this folder)")
    parser.add_argument("-o", "--output", default="documentary.html", help="where to write the film (default: documentary.html)")
    parser.add_argument("--brief", action="store_true", help="print the facts for each chapter (for writing narration) and stop")
    parser.add_argument("--script", help="a JSON file with your own title and chapter narration")
    parser.add_argument("--title", help="the film's title (default: the repository's name)")
    parser.add_argument("--everything", action="store_true", help="also count lockfiles and vendored or generated files")
    parser.add_argument("--open", action="store_true", help="open the film in your browser when it's ready")
    args = parser.parse_args()

    where = Path(args.repo).expanduser()
    found = subprocess.run(["git", "-C", str(where), "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    if found.returncode != 0:
        sys.exit(f"gitumentary: {where} is not inside a git repository.")
    repo = Path(found.stdout.strip())
    if subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "-q", "HEAD"], capture_output=True).returncode != 0:
        sys.exit("gitumentary: this repository has no commits yet. Every story needs a first chapter!")
    name = repo_name(repo)
    story, facts = build_story(repo, args.title or name.split("/")[-1], args.everything)
    story["repo"] = name
    if args.brief:
        print_brief(story, facts)
        return
    if args.script:
        apply_script(story, args.script)
    render(story, args.output)
    output = Path(args.output).resolve()
    t = story["totals"]
    print(f"🎬 {output}\n   " + " · ".join(plural(n, word) for n, word in [
        (len(story["chapters"]), "chapter"), (t["commits"], "commit"), (t["people"], "contributor"), (t["lines"], "line")]))
    if args.open:
        webbrowser.open(output.as_uri())


if __name__ == "__main__":
    main()
