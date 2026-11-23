---
name: gitumentary
description: Turn a git repository's history into a short animated documentary (one self-contained HTML file) with chapters, narration, plot twists and end credits. Use when the user asks for the story or history of a repo or codebase, a "documentary", "movie" or "trailer" of a project, a visual summary of how a codebase evolved, a project retrospective or anniversary post, or a fun onboarding overview of how a repo got where it is.
---

# gitumentary

You are the narrator. `gitumentary.py`, in the same folder as this file, does the counting and the animation. Your job is to write a story that is **true, specific and worth watching**.

## 1. Read the facts

```bash
python3 <this skill's folder>/gitumentary.py <repo> --brief
```

The brief lists each chapter's dates, people, newcomers, busiest and new areas, first, biggest and notable commits, sample commit messages, and the on-screen "plot twist" cards. It also includes default narration. The number of chapters is fixed, so write exactly one entry per chapter.

## 2. Dig where the story is

Pick the 3–5 most interesting moments: the first commit, a big rewrite or move, a huge deletion, a long silence, a release, or someone new taking over. Look closer before you write about them:

```bash
git -C <repo> show --stat <hash>
git -C <repo> log --oneline --since=<date> --until=<date> -- <area>
git -C <repo> tag --sort=creatordate
```

Read the README and CHANGELOG if there are any. Specifics make the film. "In June 2019 David moved 8,167 lines into src/" beats "the codebase was reorganized".

## 3. Write `script.json`

Put it in a temporary or scratch location, not inside the user's repository unless they ask.

```json
{
  "title": "Flask",
  "tagline": "The life of a microframework",
  "chapters": [
    { "title": "Stuff That Exists So Far", "narration": "On April 6, 2010, ..." }
  ]
}
```

- **Titles**: 2–5 words. Make them evocative but true, like "The Crowd Arrives" or "Moving House".
- **Narration**: 2–4 sentences and at most ~70 words per chapter. It plays one sentence at a time as subtitles, so every sentence must stand alone. Use a documentary voice: concrete, a little dramatic, never cheesy. End the last chapter with a line that lands.
- **Never invent facts.** Every number, date, name and event must come from the brief or from git. Check the order of events before you write "after" or "then". Don't guess at motives; if you infer something, hedge it ("It seems...").
- Name people exactly as git shows them. Bots can be part of the cast.

## 4. Render

```bash
python3 <this skill's folder>/gitumentary.py <repo> --script script.json -o <output>.html --open
```

Write the film where the user asked for it. If they didn't say, write `documentary.html` in the current folder.

## 5. Hand it over

Tell the user where the file is and how to use it:

- **Space** pauses, **← / →** jump between chapters, and **F** goes fullscreen.
- **H** hides the controls, for a clean screen recording to share.
- Adding `#t=42` to the file's URL opens the film paused at that second.

The film is a single HTML file, so it works offline, can be put on any static host, and contains no email addresses. It does include contributor names and commit messages, so remind the user of that before they share a film of a private repository.
