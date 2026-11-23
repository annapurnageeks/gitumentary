# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-23

The first release.

### Added
- `gitumentary.py`: turns any git repository's history into a single self-contained HTML film, using only the Python standard library.
- Films with an animated treemap of the codebase, chapters cut at release tags and long pauses, narration subtitles, plot-twist cards (biggest deletion, longest silence, line and contributor milestones) and end credits.
- `--brief` prints each chapter's facts, `--script` uses custom narration, `--everything` includes lockfiles and vendored code.
- Player controls: play and pause, chapter jumps, speed, fullscreen, a clean mode for screen recording (H), and `#t=` links to a moment.
- `SKILL.md`: an agent skill, so Claude Code and other agents can research a history and write the narration.
- Gallery films of React (2013–2026) and Flask (2010–2026).
- Test suite and CI on Python 3.9 and 3.13.

### Fixed
- Commits with out-of-order timestamps, such as those from an imported repository, no longer distort the timeline or create fake silences.

[0.1.0]: https://github.com/annapurnageeks/gitumentary/releases/tag/v0.1.0
