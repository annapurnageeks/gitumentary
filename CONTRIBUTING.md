# Contributing to gitumentary

Thanks for helping! gitumentary is deliberately small: one Python file, one HTML player, no dependencies. Please keep it that way, and keep the code readable.

## Ways to help

- **Share a film.** Made a gitumentary of a project you love? [Share it](https://github.com/annapurnageeks/gitumentary/issues/new?template=share-a-film.yml). The best ones go in the gallery.
- **Report a wrong fact.** If a film says something its git history doesn't support, that's a bug. [Report it](https://github.com/annapurnageeks/gitumentary/issues/new?template=bug_report.yml) with the repository and the line that's wrong.
- **Pick an idea** from the list in the [README](README.md#ideas-and-contributions-welcome).

## Development

```bash
git clone https://github.com/annapurnageeks/gitumentary
cd gitumentary
python3 -m unittest discover tests      # run the tests
python3 gitumentary.py . --open         # make a film of gitumentary itself
```

- `gitumentary.py` reads the history, builds the chapters and writes the film.
- `player.html` is the template every film is made from. Edit it, then re-run `gitumentary.py` to see your change.
- `SKILL.md` is the set of instructions an AI agent follows to narrate a film.

## Pull requests

1. Keep each pull request focused on one change.
2. Add or update a test in `tests/` when you change how history is read or counted.
3. Make sure `python3 -m unittest discover tests` passes. CI runs it on Python 3.9 and 3.13.
4. Use a [conventional commit](https://www.conventionalcommits.org/) style title, such as `fix(history): ...` or `feat(player): ...`.

## Ground rules

- **Truth first.** Everything a film shows must come from the git history. No invented facts, ever.
- **No new dependencies** in `gitumentary.py` or in the films it makes.
- **Privacy.** Films never include email addresses.

By contributing, you agree that your contributions are licensed under the MIT License.
