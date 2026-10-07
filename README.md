# oknowledge

Paste a link, get a note. oknowledge downloads the page, summarizes it with an
AI engine that needs no API key, gives it a category and tags, and writes it as
a Markdown note into your Obsidian vault. Later you browse and search the
library from the Omarchy bar or a local web page.

![The library](preview.png)

## What it does

- Takes a URL (article, YouTube video, GitHub repository, PDF, Reddit thread,
  or anything else with readable text) and extracts its text. No extractor runs
  JavaScript or opens a browser: a page that needs one is saved as incomplete.
- Analyses the text with a local or free AI engine and writes
  `<vault>/oknowledge/links/YYYY-MM-DD-<slug>.md` with a summary, key points,
  a category and 3 to 8 tags, plus one index note per category.
- **Never loses a link.** If extraction or the AI fails, the note is still
  created, marked `status: partial`, and can be finished later.
- Ships an Omarchy bar widget (paste or save from the clipboard) and a local
  web UI (library, search, categories, settings).

There is no database. The vault is the only source of truth, and every index is
rebuilt by reading the Markdown.

## Install

Requirements: Python 3.13 or newer, `yt-dlp` on the PATH (it ships with
Omarchy), Omarchy for the bar widget, and at least one AI engine (see
[Engines](#engines)).

**1. The Python package, in its own venv.** The plugin calls this exact path, so
use it:

```bash
python -m venv ~/.local/share/oknowledge/venv
~/.local/share/oknowledge/venv/bin/pip install /path/to/oknowledge
```

For development use `pip install -e '/path/to/oknowledge[dev]'` instead.

**2. The config file**, `~/.config/oknowledge/config.toml`. Only `vault` is
required; everything else has a default:

```toml
vault = "/home/you/Documents/obsidian"   # notes go to <vault>/oknowledge/
folder = "oknowledge"                    # the folder inside the vault
default_content = "full"                 # "full" keeps the original text, "summary" does not
batch = 10                               # links the web UI analyses per Analyse click

[ai]
chain = ["opencode"]                     # engines to try, in order
language = "es"                          # language of the generated content: "es" or "en"
mentions = "tools"                       # what to list for a YouTube video: "tools", "all" or "discussed"

[ai.opencode]
model = "opencode/ling-3.1-flash-free"   # default

[ai.ollama]
model = "qwen2.5:7b"                     # must be a model you have pulled
url = "http://localhost:11434"

[ai.api]
provider = "anthropic"                   # "anthropic" or "openai"
model = "claude-sonnet-5"
key_env = "ANTHROPIC_API_KEY"            # read the key from this environment variable

[web]
port = 8787
idle_timeout = 900                       # seconds; 0 = never shut down
```

Keep the file readable only by you (`chmod 600`) if it holds an API key.

**3. The bar plugin.** Copy the folder; do not symlink it, because
`omarchy plugin validate` rejects symlinked plugin directories:

```bash
cp -r plugin ~/.config/omarchy/plugins/io.github.ferc10110.oknowledge
omarchy plugin validate ~/.config/omarchy/plugins/io.github.ferc10110.oknowledge
omarchy plugin enable io.github.ferc10110.oknowledge
```

A change to the plugin's code needs a shell restart to take effect. Copy the
folder again after pulling an update.

**4. A keybinding (optional)** in `~/.config/hypr/bindings.lua`, to save the
clipboard without opening anything:

```lua
o.bind("SUPER + ALT + SHIFT + K", "Save to oknowledge", "omarchy-shell io.github.ferc10110.oknowledge save")
```

`SUPER + ALT + K` looks natural but is Omarchy's stock "Tmux keybindings", so
this uses `SUPER + ALT + SHIFT + K`. `SUPER + ALT + O` and `SUPER + ALT + L` are
also unused by default if you want something shorter.

## Use

**The bar.** Open the panel: if the clipboard holds a URL it is offered with
two buttons, **Full** and **Summary**. The icon shows a count while links are
being processed, and the panel lists recent and unfinished links, with Retry
and a button that opens the library.

A link that fails permanently (a page that will never yield text) keeps the
count red, because the link really is unfinished. The way out is to delete it
from the web UI. A link whose note *did* land, and whose entry only looks
unfinished, is cleared by `retry` without rewriting the note.

**The terminal.** Global option `--config PATH` goes before the subcommand.

| Command | What it does |
|---|---|
| `oknowledge add URL [--full\|--summary] [--engine NAME] [--reprocess] [--json]` | process one link end to end |
| `oknowledge status [--json]` | note count, and every link that is pending, partial or failed |
| `oknowledge reindex` | rebuild every category index from the notes |
| `oknowledge retry [--limit N] [--json]` | finish the links left half done, newest first (see the note below) |
| `oknowledge mentions [--limit N] [--json]` | add the list of what a video names to the videos already saved (see the note below) |
| `oknowledge icons` | fetch the favicon of every site in the library, once per site |
| `oknowledge import FILE [--dry-run] [--json]` | import the links out of a WhatsApp export, dated when you sent them |
| `oknowledge serve [--open]` | start the web UI |

**`import` reads a WhatsApp chat export** (`Export chat` → `Without media`,
which gives a `_chat.txt`) and saves every link in it as an unfinished note
dated the day you sent it. Phone numbers, notes to self and anything else
without a link are skipped. Nothing is analysed: that is `retry`'s job, and
`retry --limit 50` does it in batches.

Run it with `--dry-run` first. It lists what it would capture in three
groups — the links written with `https://`, the ones written as a bare
domain, and the messages that looked like they had a link and did not match.
The second group is where a false positive would be; the third is where a
missed link would be.

**From the browser:** Settings → Import a WhatsApp export. It takes the `.zip`
WhatsApp gives you or the `.txt` inside it, and there the dry run is not
optional: choosing the file shows what it found and writes nothing until you
press the button. It says how it read the dates and lists every bare domain,
which are the two things a written note no longer shows. The upload is held
in `~/.local/state/oknowledge/import/` between the two steps and deleted when
you confirm; one nobody confirmed is swept an hour later.

Saving the same link twice gives one note (`already saved`). Pasting a link
whose note is `partial` finishes it instead.

**`retry` finishes what is unfinished, and nothing else.** It looks at the
queue, not at your vault, and takes every entry that is `partial` or `failed`
plus every `pending` entry no live process is working on. Then, for each one,
it asks the vault first:

- **The note is there and its status is not `partial`** — the note is finished,
  so `retry` writes nothing. It marks the entry `ok` and moves on, saying *the
  note is already saved and finished, so the queue entry was brought into line
  with it instead of re-analysing the link*. No page is fetched, no engine is
  asked.
- **The note is `partial`, or there is no note** — this is the case `retry` is
  for: the link is processed the rest of the way, and the note is written or
  finished.
- **Another process holds the link** — it is left alone and reported as
  `pending`, for whoever holds it.

This matters because a queue entry can outlive the work it describes. If the
process is killed between writing the note and recording that it finished —
restarting the Omarchy shell mid-save does it — the entry stays `pending`
forever while the note on disk is complete. Weeks of your own writing can be
sitting in that note. `retry` treats the note as the real artifact and the
queue as bookkeeping: when they disagree and the note is finished, it is the
bookkeeping that gets corrected.

One consequence, on purpose: a link saved as a summary whose entry asked for
full content stays a summary. `retry` will not upgrade it, because it cannot
tell an untouched note from one you spent an evening on. Ask for the upgrade
when you want it, with `add --reprocess` or the web's Reprocess button — the
one thing that does replace a note's content.

`retry` never touches a note that has no queue entry, and never touches a file
without the `oknowledge: 1` marker. Exit 1 means some links are still
unfinished; `--json` prints one object per link with what happened to it.

`--limit N` finishes at most N links and stops, newest first. That is how a
large import gets analysed: 1215 links are 10 to 20 hours of fetching and
model time, so `oknowledge retry --limit 50` once a day works through them
without a run that never ends. The quota counts links it actually worked on,
so an entry that turned out to be already saved does not use one up. The exit
code describes those links and not the backlog behind them: a limited run
exits 0 when the links it worked on are fine, and 1 when one of them is still
unfinished.

**`mentions` gives the videos already in the library their list.** A YouTube
note now carries what the video named, written when the link is first
processed; this command does the same for the ones saved before. It writes the
mentions section and nothing else: the title, the summary and the points you
have already read are left as they are. It asks each video once, even when the
answer is empty, so running it again only looks at videos it never asked. A
note saved with its full text reuses it, so most of a run needs no network.
`--limit N` stops after N videos, newest first, and the exit code describes
those videos and not the backlog behind them. It spends model calls on your
library, so it runs only when you type it, never by itself. A note whose
`## Menciones` heading has nothing under it was asked and the video named
nothing; that is not a broken note.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | it worked |
| 1 | it ran, but the link is unfinished: a partial note, an entry locked by another process, a `retry` that left some links undone, or a `mentions` run with a video it could not finish |
| 2 | your input or config is wrong: bad arguments, an empty URL, a missing or malformed config, a port already in use |
| 3 | something unexpected: a disk or permission error, a refused write, a bug |

**A nonzero exit does not mean the link was lost.** Exit 1 means the note
exists but is not fully analysed. Exit 3 prints whether the link reached the
queue. The rule the project is built around is that a link is never lost.

### The web UI

`oknowledge serve` prints `oknowledge: the library is at http://127.0.0.1:8787/`
to stderr and, with `--open`, opens the browser. Screens: Library (cards, filter
by category and tag), Search (title, summary, points, tags, what a video
mentioned and full text, with the matching fragment), Item (change category, edit tags, reprocess, delete),
Categories (rename and merge, rewriting the affected notes and indexes),
Import (a WhatsApp export, previewed before it is written), Analyse (a batch of
the links that are still waiting, with a bar) and Settings.

- It shuts itself down after `idle_timeout` seconds without requests (default
  900; `0` means never). The watchdog polls every 5 seconds, so the shutdown
  can be up to 5 seconds late.
- A request that hangs forever keeps the server up forever. That is deliberate:
  the alternative would kill an analysis that is still running.
- If the port is taken it exits with code 2 and suggests setting `web.port`.
- **Delete moves the note to `<vault>/oknowledge/trash/`**, so you can recover
  it from Obsidian. Nothing in this project unlinks a note.
- **A card whose note was never analysed has an *Analyse it* button**, and it
  does not stop to ask: there is no analysis in that note yet to write over.
  The button on the note's own page does ask, because there usually is one.
  Either way the work happens after the answer is sent, so the browser does
  not wait for a model.
- **The Analyse page runs a batch of them.** `batch` in the config says how
  many (default 10), the page draws a `<progress>` bar and comes back on its
  own every 10 seconds; closing the tab does not stop the run. One batch at a
  time: a second click while one is in flight is refused rather than starting
  a second run over the same links. The progress is held in memory, so a
  server that restarts mid-batch loses the bar and no links -- what is still
  owed is in the queue on disk, and the next run picks it up.
- **Saving settings rewrites the config file.** Comments and keys it does not
  know are not preserved; the previous file is kept as `config.toml.bak`.
  Settings are always saved to `~/.config/oknowledge/config.toml`, whatever
  `--config` says.

## The vault

```
<vault>/oknowledge/
  Networking.md              category index, generated
  links/
    2026-10-03-wireguard-vs-openvpn.md
  attachments/               cover images
  trash/                     notes deleted from the web UI
```

A note:

```markdown
---
url: https://example.com/article
title: WireGuard vs OpenVPN
category: Networking
tags: [vpn, privacy, wireguard]
type: article        # article | youtube | github | pdf | social | other
source: example.com
saved: 2026-10-03
content: full        # full | summary
status: ok           # ok | partial | failed
id: 9f2a1c4b8e07
oknowledge: 1
---

# WireGuard vs OpenVPN

(summary)

## Key points
## Original content    <- only with content: full
```

Frontmatter keys, file names and code are in English. The summary, points,
category and tags come out in the language of `[ai] language`.

**Editing by hand is part of the design.** Change `category` or `tags` in
Obsidian and run `oknowledge reindex`: the indexes follow. Delete a note and it
leaves its index.

**The safety rules.** oknowledge writes only inside `<vault>/oknowledge/`, and
only into files whose frontmatter has `oknowledge: 1`. A file without that
marker is never modified or deleted, even inside that folder.

**`status` is a contract.** `partial` is ours: the machinery may rewrite it. Any
other value, including one you type yourself (`status: done`, `reviewed`), is
yours: the machinery will not overwrite that note on its own. An explicit
reprocess (the web's Reprocess button, or `add --reprocess`) is the one thing
that replaces a note's content, because that is what asking for a fresh
analysis means.

## Engines

`[ai] chain` is both the switch and the priority: engines are tried in the
order listed, and an engine not in the list is never used. `--engine NAME`
forces one for a single link.

| Engine | How | Leaves your machine |
|---|---|---|
| `opencode` | `opencode run --pure` in an empty temp directory | yes, to opencode's gateway |
| `ollama` | local `/api/chat` with JSON output | **no**: the only fully local engine |
| `api` | Anthropic or OpenAI, with your key | yes, to the provider |

If `ollama` is in the chain and installed but not running, oknowledge starts it
through its systemd user unit (or a detached `ollama serve`) before giving up.

**The API key** is never written to the vault or the repo. Put it in an
environment variable named by `key_env`, or in `key` in the config file (keep
it `chmod 600`).

**`fake` is a test double.** It shows up in `oknowledge add --engine --help`
because it is a valid engine name, but it only replays canned replies for the
test suite. Do not select it: it produces no real analysis.

## The two languages

They are independent, and it is common to mix them up.

| | Where it comes from | Default | Supported |
|---|---|---|---|
| Interface (panel, web UI) | `~/.config/omarchy/plugin-language.json`, e.g. `{"language": "es"}`, shared with the other Omarchy plugins | English | `en`, `es` |
| AI content (summary, points, category, tags, index boilerplate) | `[ai] language` in `config.toml` | `es` | `es`, `en` |

An English interface with Spanish summaries is the normal setup. Changing the
interface language never touches saved notes, and changing the content
language only affects notes saved afterwards. Hand-set values outside the
supported ones are not supported: the settings page then shows no radio
selected, and generated boilerplate falls back to English.

## Known limits

- **First page load is slow on a big library.** Building the search index was
  measured at 6.1 seconds for 3000 notes. It is not broken.
- **Reddit can answer a default User-Agent with 403.** Then the note is saved
  as `partial`. X, Instagram and TikTok usually block as well.
- **Localhost and LAN URLs are fetched on purpose.** oknowledge does not filter
  private addresses.
- **Analysis speed is your machine's.** The engines run locally (or on a free
  gateway), so a link can take from seconds to a minute or more.
- Pages that need JavaScript or a login become `partial`.
- PDFs: first 20 pages, text layer only (no OCR).

## Files

| Path | What |
|---|---|
| `~/.config/oknowledge/config.toml` | your config (and `.bak` after a web save) |
| `~/.config/omarchy/plugin-language.json` | shared interface language |
| `~/.config/omarchy/plugins/io.github.ferc10110.oknowledge/` | the plugin |
| `~/.local/share/oknowledge/venv/` | the Python environment |
| `$XDG_STATE_HOME/oknowledge/` (default `~/.local/state/oknowledge/`) | `queue/` and `locks/`, one file per link |
| `<vault>/oknowledge/` | your notes |

## Remove

```bash
omarchy plugin remove io.github.ferc10110.oknowledge
rm -rf ~/.local/share/oknowledge ~/.local/state/oknowledge ~/.config/oknowledge
```

Your notes in `<vault>/oknowledge/` are left alone; delete that folder yourself
if you want them gone. Remove the keybinding line from `bindings.lua` too.

## Development

```bash
python -m venv ~/.local/share/oknowledge/venv
~/.local/share/oknowledge/venv/bin/pip install -e '.[dev]'
~/.local/share/oknowledge/venv/bin/python -m pytest -W error     # Python
(cd plugin && node --test)                                       # plugin logic
omarchy plugin validate plugin
```

No test touches the network. Layout:

```
src/oknowledge/
  cli.py         add, import, status, reindex, retry, serve
  pipeline.py    one link end to end; queue.py the state files
  whatsapp.py    an export to dated links; no disk, no network
  extract/       article, youtube, github, pdf, social
  ai/            opencode, ollama, api, fake; prompts/analyze.txt
  vault.py       the only layer that writes Markdown
  web/           FastAPI app, templates, static
plugin/          the Omarchy plugin (manifest.json, QML, JS)
docs/            design and plan
```

## License

MIT
