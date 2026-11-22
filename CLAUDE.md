# CLAUDE.md

This repository is the Parrot Cart plugin registry and the site built from
it, at https://plasticbugs.github.io/parrot-cart-plugins/. The site has the
home page with the newest plugins, All plugins (`/plugins/`, with search,
filters and pages) with direct `.CVP` downloads, a page for each plugin, the
submit page, the movie converter (`/converter/`) and the developer portal
(`/developers/`). Everything is static, built by Python scripts that use
only the standard library.

## Layout

| Path | What |
|---|---|
| `plugins/<id>.json`, `plugins/<id>/` | one entry per listed plugin, and its files: the .CVP, screenshots, README.md, the cart's README text |
| `examples/` | entries for plugins with nothing to download (only Movies, which is built into the cart). `tools/seed_examples.py` writes them |
| `site/copy.toml` | every word on the site and in our replies on issues and pull requests. The owner edits it by hand |
| `site/assets/` | `tokens.css`, `base.css`, `site.css`, `site.js`, `browse.js` (All plugins) |
| `site/data/menu.json` | the cart menu's font, for drawing its screens (`tools/import_menu_font.py`) |
| `developers/` | the portal's words (`copy.toml`), its ready-made icons (`icons.toml`) and assets. Its pages come from the starter kit's docs |
| `converter/` | the movie converter, a built copy of the browser app |
| `registry.config.json` | limits, labels, the shop link, the template repo, `show_examples`, and the allowed `tags` and `works_with` (their names are in `site/copy.toml`, `[browse.types]` and `[browse.works_with]`) |
| `tools/` | the builders, the validator, the CI scripts (`tools/ci/`) |
| `tests/` | the unit tests and the workflow lint |

## Commands

```sh
python3 -I -m unittest discover -s tests -v       # the tests
python3 -I tests/lint_workflows.py                # the workflows and the issue form
python3 -I tools/registry.py check                # every entry against the schema
python3 -I tools/build_site.py --out _site        # the site, registry.json and plugins/index.json
python3 -I tools/build_dev.py --kit ../parrotcart-plugin-template --out _site/developers
```

Build the site before the portal, into the portal's parent folder. Without
`--kit`, `build_dev.py` looks for `kit/` here, then for a checkout of the
starter kit beside this repository.

## Adding or updating a plugin by hand

```sh
export GITHUB_TOKEN=$(gh auth token)
python3 tools/validate.py OWNER/REPO [--tag vX.Y.Z] [--description "..."] [--tags games,music] [--works-with keyboard,mouse] --write
```

- It checks the release the way a submission is checked and writes
  `plugins/<id>.json` and the files. Without `--tag` it takes the latest
  release.
- Set `GITHUB_TOKEN`. Without it, GitHub's limit for anonymous calls stops it
  after a few runs, and the error says so.
- Running `--write` again for a version that's already listed reports
  "already listed" and keeps the old files. To pick up a changed release
  asset (new screenshots, say), `git checkout` the entry and its folder
  first, then write again.
- After a release asset is replaced, GitHub can serve the old file for a
  minute. The validator then reports a size mismatch. Wait and retry.
- The screenshots our plugins use are the cart's menu pages, drawn by
  `tools/tvscreen.py` (`seed_examples.shots(entry)`). They show the version,
  so they're redrawn for each release.
- After changing `seed_examples.py`, run `python3 tools/seed_examples.py`.
  A test checks that `examples/` is what it writes.
- `tags` (one or two types) and `works_with` (USB and MIDI devices) are
  optional. The form sets them on a submission, an update keeps them, and
  `--tags` and `--works-with` set them by hand. Only give a `works_with`
  that the plugin's README says it supports. A new type or device goes in
  `registry.config.json`, its name in `site/copy.toml` and the issue form
  (the workflow lint checks they match).

## Workflows

- **Site** (`pages.yml`): every push to `main` checks the entries, builds the
  site and the portal (from the starter kit's `main`) and deploys Pages.
- **Tests** (`tests.yml`): every push and pull request. A pull request that
  changes an entry is checked against its release on GitHub.
- **Plugin submission** (`submission.yml`): an issue from the Submit form. It
  reads the plugin's repository with a read-only token, comments the result
  and opens a pull request for review. It never runs code from a submitted
  repository, and the issue's text reaches the scripts only through the API.
  Keep it that way.
- **Plugin updates** (`updates.yml`): daily at 06:17 UTC, a pull request for
  each listed plugin with a newer release that passes.

## Rules

- No ROMs, BIOS files, game data or commercial game art in entries,
  screenshots or examples.
- IDs that start with `parrotcart.` are for the plugins we make.
- The words are plain, short and friendly, written with "we" and "you", the
  way a person writes. No em dashes, no taglines, no "the X's own Y", no
  explaining the machinery (bots, pull requests) to plugin authors, and no
  advice on how to read a page. Plugin descriptions are a noun phrase with no
  period, like "Emulator for the handheld console". Validation messages and
  replies follow the same rules.
- The top of `site/assets/site.css` is the Hallmark stamp, the record of the
  design's decisions (`.hallmark/log.json` has the build log). Keep it at the
  top, and update it when a change undoes one of them.
- Commit with the no-reply identity (`plasticbugs@users.noreply.github.com`)
  and check `git log -1 --format='%an %ae %cn %ce'`. Nothing personal goes
  in this public repository.
