# CASSim

A free, installable family of calculator and programming apps that runs entirely in your browser.
The current all-in-one build contains Nspire, Pseudocode & Python and Scientific apps, with
ClassPad and Prime available as future choices.

**Try it: <https://cassim-app.pages.dev/>** (installable as an app; works offline after setup).

| Site | Address | What it is |
|---|---|---|
| CASSim (stable) | <https://cassim-app.pages.dev/> | The released all-in-one app. |
| CASSim (testing) | <https://cassim-calc.pages.dev/> | The newest all-in-one build, updated on every merge. May break. |
| Help | <https://cassim-wiki.pages.dev/> | The user guide; the app's Help link opens it. |

Built for the VCE Mathematics courses, but should be more generally useful.
Usable on a desktop, laptop, netbook (Chromebook), tablet or a phone.

> **Status: in development.** The all-in-one Home shell is working. Nspire has Calculator, Graphs,
> Lists & Spreadsheet and Data & Statistics; Pseudocode has an integrated editor, run/step and
> trace-table app. Python execution, translation, Notes and later profiles are still in progress.
> See [PLAN.md](PLAN.md) and [docs/SRS.md](docs/SRS.md).

CASSim is an independently made simulator for educational purposes.
Each calculator app's behaviour, layout and menu structure is designed to be familiar to users of
that calculator without being an exact copy. The first calculator is the TI-Nspire CX CAS; future
devices keep their own behaviour and corpus.
It is not affiliated with, endorsed by or sponsored by Texas Instruments. 
It is not an approved exam calculator and must not be used in assessments that require an approved device. 
TI-Nspire is a trademark of Texas Instruments.

### Design and IP

CASSim's calculator apps mirror the relevant layout, menus and commands so that practice transfers
to the real calculator. All artwork and help text are CASSim's own. Nspire behaviour was learned by using
TI's software as a user, typing inputs and recording the outputs; nothing was decompiled. It is not
an approved exam calculator. The rule is written up in
[docs/decisions/0028-ip-boundary-and-clean-room.md](docs/decisions/0028-ip-boundary-and-clean-room.md).

**Wolfram Language and Mathematica.** There are no plans to implement the Wolfram Language or
Mathematica in CASSim. If that is what you need, see **Woxi** (<https://github.com/ad-si/Woxi>,
docs at <https://woxi.ad-si.com/>), an open-source interpreter for a subset of the Wolfram
Language with a notebook editor, Woxi Studio. CASSim and Woxi are separate, unaffiliated
projects. Wolfram Language and Mathematica are trademarks of Wolfram Research.

## What it does

- **Home chooser** for the all-in-one app, opened on every launch, with disabled future
  choices.
- **Nspire calculator app** with an Nspire-like keypad, numbered menus, 2D templates (fractions, roots,
  piecewise, systems, calculus) and the document, problem and page model.
- **Nspire CAS engine** (SymPy and mpmath through Pyodide) that parses TI syntax with a real tokenizer
  and parser. Results are judged by symbolic and numeric equality, not TI's exact text.
- **Data and graph pages** for spreadsheets, statistics, charts and function plotting, sharing the
  Problem's variables.
- **Two views**: Handheld (a keypad you tap or type on) and Computer (a laptop layout).
- **Pseudocode & Python app** with a standalone editor, pseudocode execution and vertical/horizontal
  trace views. Python execution and translation remain planned.
- **Private and offline.** No server, no telemetry, no account. Wait for “Offline: Ready” in the CASSim menu
  before disconnecting. Documents are saved in browser storage or as files
  or shared as a link that carries the document in the URL fragment.
- **Open and Save, Import and Export.** In every app, Open, Save and Save As keep your work by
  name inside the app (browser storage, or the desktop app's own storage), with no file dialog.
  Import and Export are the only menu items that read or write a file: CASSim's own
  `.cassim.json` for calculator documents, `.py` and `.pseudo.txt` for code. TI's `.tns` files
  cannot be opened or saved; if that is ever added it will be under Import and Export.

## Related software

The calculator makers sell their own computer and phone versions, and there are free CAS programs
too. The help page [Other calculators and CAS software](https://cassim-wiki.pages.dev/Other-calculators-and-CAS-software)
compares them for the TI-Nspire CX CAS, ClassPad II and HP Prime G2, and for the computer-based
exam options (Mathematica, Maple, MATLAB).

## How it is tested

A corpus of 186 and counting calculator cases was tested on the TI-Nspire CX CAS and reviewed, 
and every case replays against the engine in CASSim. See `python -m tools.replay` for
progress and [docs/testing/TESTING.md](docs/testing/TESTING.md) for the method.

This repository holds the cases and the written results. The simulator screenshots they were
transcribed from are kept in a separate evidence repository; a screenshot path named in a case
or a results file refers to that repository
([docs/decisions/0039-evidence-repository.md](docs/decisions/0039-evidence-repository.md)).

## Try it

You need [uv](https://docs.astral.sh/uv/). Python 3.14 is installed by uv.

```
uv sync --group web
uv run cassim                         # the app in a window (for development)
uv run cassim --web                   # the app in your browser (for development)
uv run cassim --app pseudocode        # skip Home and open one app (nspire, pseudocode or scientific)
uv run cassim --view handheld         # choose the view (handheld or computer)
uv run cassim --course methods        # the app with the Methods settings
uv run cassim --text                  # text interface, like the Calculator page
uv run cassim -c "solve(x^2=2,x)"     # one entry, then exit
uv run python -m tools.publish        # build the installable offline site (--bundle all|tin|pseudo)
```

The text interface is described in [docs/user/repl.md](docs/user/repl.md).
The development `--web` server does not include the published site's browser context-menu routing.

**Deep links.** The all-in-one app opens to Home on every launch. A link can open one app directly
instead; this works on the published sites and on a local build of `tools.publish`:

| Link | Opens |
|---|---|
| `https://cassim-app.pages.dev/#/app/nspire` | the Nspire calculator |
| `https://cassim-app.pages.dev/#/app/pseudocode` | Pseudocode & Python |
| `https://cassim-app.pages.dev/` | Home |

The short forms `#/nspire` and `#/pseudocode` work too, and `cassim-calc` (testing) takes the same
links. A share link (`#/doc=...`) opens the app its document belongs to. A link naming an app that
is not in the bundle shows Home; a single-app site (`cassim-tin`, `cassim-pseudo`, `cassim-sci`) ignores the link
and opens its one app. Developer `#/debug` routes open the first app for the browser tests.

## Builds

CASSim is released as a **static web site** (`tools.publish`). It is the only supported build and the
only one tested: copy `build/web` to the root of any static host, or pass `--base-url SUBPATH` to
serve it below a sub-path. Users can install it as an app (PWA); once the offline-ready indicator
appears, it works offline. Clearing browser storage removes the offline installation.

The stable and testing sites are the all-in-one app. The build can also produce CASSim-TIN and
CASSim-pseudo bundles now; CASSim-CP and CASSim-Prime remain future builds. See
[PLAN.md](PLAN.md) section 15 for site and release status.

## Publishing

The sites are Cloudflare Pages projects, deployed by `.github/workflows/deploy.yml` with
`wrangler pages deploy`. Nothing is deployed from a developer's machine in normal use.

| Project | Built from | Deployed when |
|---|---|---|
| `cassim-calc` (testing) | `python -m tools.publish --bundle all` | every merge to `main` |
| `cassim-wiki` (help) | `python -m tools.wiki_site`, from `docs/wiki/` | every merge to `main` |
| `cassim-app` (stable) | `python -m tools.publish --bundle all` | a published GitHub release |
| `cassim-tin` (the Nspire alone, stable) | `python -m tools.publish --bundle tin` | a published GitHub release |
| `cassim-pseudo` (Pseudocode & Python alone, stable) | `python -m tools.publish --bundle pseudo` | a published GitHub release |
| `cassim-sci` (the Scientific calculator alone, stable) | `python -m tools.publish --bundle sci` | a published GitHub release |

**Testing and help.** Merge a pull request into `main` (CI's `check` job must pass). The Deploy
workflow then builds and publishes both. Edit the help pages in `docs/wiki/`; a `[[Page name]]` link
to a page that does not exist fails the build.

**A stable release.**

1. Check the testing site: <https://cassim-calc.pages.dev/> loads, evaluates, and reloads offline.
2. Set `version` in `pyproject.toml` in a pull request and merge it. The About dialog shows this
   version; the offline cache is renewed on every build whether or not the number changes.
3. Publish a release whose tag matches: `gh release create v0.2.0 --generate-notes`. The Deploy
   workflow builds that commit and publishes it to `cassim-app`.
4. Open <https://cassim-app.pages.dev/>. An installed copy indicates an available update in the CASSim menu.

**By hand.** Actions > Deploy > Run workflow, target `testing` or `stable`, or
`gh workflow run deploy.yml -f target=stable`.

**Rolling back.** In the Cloudflare dashboard, open the project's Deployments and choose
"Rollback to this deployment" on an earlier one, or publish a new release from a fixed `main`.

**Set-up (done once).** The workflow needs two repository secrets: `CLOUDFLARE_API_TOKEN` (a token
with Account > Cloudflare Pages > Edit) and `CLOUDFLARE_ACCOUNT_ID`. A new Pages project is made
with `npx wrangler pages project create NAME --production-branch main`.

Each site is its own origin: an installed app, its autosaved document and its settings belong to
the site they were made on. Move a document between sites by saving it to a file or a share link.

The window opened by `uv run cassim` is for development. Native desktop (Windows, macOS, Linux) and
mobile (Android, iOS) builds with `flet build` are possible later but not started; see
[PLAN.md](PLAN.md) section 13 and NFR-PORT-004 in [docs/SRS.md](docs/SRS.md).

## Development

```
uv run ruff format && uv run ruff check
uv run ty check
uv run pytest -m "not e2e"            # fast suite; add -m slow for the long simulations
python -m tools.replay                # corpus progress
```

- Core engine (`src/cassim/core`) is pure Python, never imports Flet and passes Ty strict.
  SymPy is touched only in `core/compat/sympy_adapter.py`.
- Every behaviour change ships with a test that cites the SRS requirement ID where one applies.
- Layout: `app` (multi-app shell), `devices` (plug-in device packages), `core` (Nspire engine),
  `device` (shared framework), `doc` (documents), `runtime` (pseudocode), `tools` (build and corpus
  scripts), and `corpus` (golden cases).

## Documents

| | |
|---|---|
| [PLAN.md](PLAN.md) | Architecture, milestones, open work |
| [docs/SRS.md](docs/SRS.md) | Requirements with stable IDs and MoSCoW priorities |
| [docs/decisions/](docs/decisions/) | Decision records and spike results |
| [docs/testing/](docs/testing/) | Test method and emulator comparison results |
| [AGENTS.md](AGENTS.md) | Shared working brief for AI-assisted development |

## Licence

Released under the [MIT licence](LICENSE), copyright (c) 2026 Simon Tyler and CASSim contributors. Third-party
notices for Flet, Pyodide, SymPy, mpmath, CodeMirror, Flutter and the bundled fonts are in the
app's About dialog; Flutter's full list is `assets/NOTICES` on each site.

No TI logos, artwork or ROM content are included. 