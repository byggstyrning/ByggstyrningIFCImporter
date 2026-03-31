# Archive — alternate routes and retired experiments

This folder holds **documentation and scripts from approaches we tried but did not keep** (superseded, blocked, or abandoned). The goal is a lightweight history so future work does not repeat the same dead ends, without mixing these artifacts into production paths.

## What belongs here

- Short **notes** (Markdown): what we tried, why it seemed plausible, what failed (error, limitation, or decision), and what replaced it if anything.
- **Scripts** or snippets copied from chats or one-off branches: PowerShell, Python, journal fragments, etc.
- Pointers to **commits, PRs, or issues** if the attempt lived in version control elsewhere.

## What does not belong here

- Active tooling used by the pipeline (keep those under `scripts/rbp/`, `tools/`, `lib/`, etc.).
- Large binary outputs or full model exports (link to paths or attach small fixtures only).

## Suggested layout

Use one subfolder per topic or attempt:

```text
archive/
  README.md                 ← this file
  <topic-slug>/
    NOTES.md                ← or README.md: context, failure mode, lessons
    ... optional scripts, supplementary files, screenshots refs
```

Examples of topic slugs: `journal-automation` (see `journal-automation/NOTES.md`), `pyrevit-ribbon-scripts` (retired `script.py` wrappers for interactive pyRevit), `inplace-convert-kit` (in-place→loadable family RFAs + pyRevit/RBP scripts), `graphisoft-api-prototype`, `rbp-room-merge-v1`.

## Naming

- Prefer **kebab-case** folder names.
- Date optional in the notes front matter or first line: `2026-03 — …` helps scanning.

## Relationship to `docs/`

- **`docs/`** — current investigations and reference the team still uses.
- **`archive/`** — tombstones for paths we explicitly left behind; cross-link from `docs/` when an investigation mentions a discarded option.
