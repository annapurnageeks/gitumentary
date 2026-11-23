"""Tests for gitumentary. Run with:  python3 -m unittest discover tests"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import gitumentary  # noqa: E402

DAY = 86400
START = 1_600_000_000  # 2020-09-13


def make_repo(folder, commits):
    """Create a git repo. `commits` is a list of (day, author, message, {path: text or None})."""
    run = lambda *args, env=None: subprocess.run(["git", "-C", str(folder), *args], check=True,
                                                 capture_output=True, env=env)
    run("init", "-q")
    for day, author, message, files in commits:
        for path, text in files.items():
            target = Path(folder) / path
            if text is None:
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
        stamp = f"{START + day * DAY} +0000"
        env = dict(os.environ, GIT_AUTHOR_NAME=author, GIT_AUTHOR_EMAIL="a@example.com",
                   GIT_COMMITTER_NAME=author, GIT_COMMITTER_EMAIL="a@example.com",
                   GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
        run("add", "-A")
        run("commit", "-q", "--allow-empty", "-m", message, env=env)


def lines(n):
    return "".join(f"line {i}\n" for i in range(n))


class StoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_counts_lines_people_and_chapters(self):
        make_repo(self.repo, [
            (0, "Ada", "Initial commit", {"src/app.py": lines(10), "README.md": lines(3)}),
            (5, "Grace", "Add tests", {"tests/test_app.py": lines(4)}),
            (9, "Ada", "Grow the app", {"src/app.py": lines(20)}),
        ])
        story, facts = gitumentary.build_story(self.repo, "demo", keep_everything=False)
        self.assertEqual(story["totals"], {"commits": 3, "people": 2, "lines": 27})
        self.assertEqual(len(story["chapters"]), 3)
        self.assertIn("Initial commit", story["chapters"][0]["narration"])
        self.assertEqual(facts[0]["first_commit"]["author"], "Ada")
        languages = {a["name"]: a["language"] for a in story["areas"]}
        self.assertEqual(languages["src"], "Python")

    def test_deleted_and_noise_files_are_not_counted(self):
        make_repo(self.repo, [
            (0, "Ada", "Start", {"a.py": lines(10), "package-lock.json": lines(500)}),
            (1, "Ada", "Remove a.py", {"a.py": None, "b.py": lines(2)}),
        ])
        story, _ = gitumentary.build_story(self.repo, "demo", keep_everything=False)
        self.assertEqual(story["totals"]["lines"], 2)
        everything, _ = gitumentary.build_story(self.repo, "demo", keep_everything=True)
        self.assertEqual(everything["totals"]["lines"], 502)

    def test_long_silence_becomes_a_card(self):
        make_repo(self.repo, [(day, "Ada", f"Commit {day}", {"a.py": lines(day + 1)}) for day in range(5)]
                  + [(200 + day, "Ada", f"Back {day}", {"a.py": lines(day + 10)}) for day in range(5)])
        _, facts = gitumentary.build_story(self.repo, "demo", keep_everything=False)
        cards = [t["text"] for f in facts for t in f["twists"]]
        self.assertIn("196 days without a single commit", cards)


class TimelineTest(unittest.TestCase):
    def times(self, days):
        commits = [{"time": START + d * DAY} for d in days]
        gitumentary.steady_times(commits)
        return [(c["time"] - START) / DAY for c in commits]

    def test_outlier_from_the_future_does_not_drag_later_commits(self):
        days = list(range(40))
        days[20] = 1000  # e.g. a commit imported from another repository with a rewritten date
        result = self.times(days)
        self.assertEqual(result, sorted(result))
        self.assertLessEqual(max(result), 39)

    def test_real_pauses_are_kept(self):
        result = self.times(list(range(13)) + list(range(100, 113)))
        self.assertEqual(result[13] - result[12], 88)

    def test_pause_after_a_slow_period_is_kept(self):
        # commits every 20 days, then 100 days of silence, then daily work (Flask, early 2025)
        days = [i * 20 for i in range(13)] + [340 + i for i in range(13)]
        result = self.times(days)
        self.assertEqual(result, days)

    def test_outlier_from_the_past_is_ignored(self):
        days = list(range(100, 140))
        days[20] = 0  # e.g. a cherry-picked commit with a very old date
        result = self.times(days)
        self.assertEqual(result, sorted(result))
        self.assertGreaterEqual(min(result), 100)

    def test_small_backwards_steps_are_smoothed(self):
        self.assertEqual(self.times([0, 2, 1, 3]), [0, 2, 2, 3])


class OutputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        make_repo(self.repo, [(0, "Mallory", "Hello </script><img src=x onerror=alert(1)>", {"x.js": lines(3)})])

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "gitumentary.py"), str(self.repo), *args],
                              capture_output=True, text=True, encoding="utf-8")

    def test_film_is_written_and_commit_messages_cannot_break_out(self):
        out = Path(self.tmp.name) / "film.html"
        result = self.run_cli("-o", str(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        html = out.read_text(encoding="utf-8")
        data = html.split('<script id="story" type="application/json">')[1].split("</script>")[0]
        self.assertIn("Hello <\\/script>", data)
        self.assertEqual(json.loads(data)["totals"]["commits"], 1)

    def test_script_replaces_narration(self):
        script = Path(self.tmp.name) / "script.json"
        script.write_text(json.dumps({"title": "My Film", "chapters": [{"title": "One", "narration": "Hi."}]}))
        out = Path(self.tmp.name) / "film.html"
        self.assertEqual(self.run_cli("--script", str(script), "-o", str(out)).returncode, 0)
        self.assertIn('"title":"My Film"', out.read_text(encoding="utf-8"))

    def test_script_with_wrong_chapter_count_is_rejected(self):
        script = Path(self.tmp.name) / "script.json"
        script.write_text(json.dumps({"chapters": [{"title": "A"}, {"title": "B"}]}))
        result = self.run_cli("--script", str(script), "-o", str(Path(self.tmp.name) / "x.html"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has 2 chapters", result.stderr)

    def test_brief_prints_facts(self):
        result = self.run_cli("--brief")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Chapter 1", result.stdout)
        self.assertIn("Mallory", result.stdout)

    def test_not_a_repository(self):
        result = subprocess.run([sys.executable, str(ROOT / "gitumentary.py"), self.tmp.name],
                                capture_output=True, text=True)
        self.assertIn("not inside a git repository", result.stderr)


if __name__ == "__main__":
    unittest.main()
