# stackfuzz

A stack-aware [`ffuf`](https://github.com/ffuf/ffuf) wrapper.

`stackfuzz` sends a single recon request to a web target, fingerprints its
technology stack from the response, and then runs `ffuf` with **curated
wordlists chosen for that stack** — instead of fuzzing blindly with one generic
list.

Supported detections: **Django**, **Next.js**, **NestJS/Express**, **Flask**,
**Laravel**. It can detect several at once, in which case their wordlists are
merged (deduplicated). If nothing is detected, it falls back to `generic.txt`.

## How it works

1. **Recon** — one `httpx` GET to the base URL, collecting response headers and
   cookies, plus a few probe paths (`/admin/`, `/_next/`, `/api/`).
2. **Detect** — signature rules over headers / cookie names / probe status codes
   (e.g. `x-powered-by: Next.js`, a `laravel_session` cookie, a `csrftoken`
   cookie, a `Werkzeug` server header).
3. **Resolve** — each detected tech maps to one or more bundled wordlists; several
   techs are merged into a single deduplicated list.
4. **Fuzz** — build and run `ffuf -u <target>/FUZZ -w <wordlist>`.

## Requirements

- Python **3.9+**
- [`ffuf`](https://github.com/ffuf/ffuf) installed and on your `PATH`
  (only needed to actually fuzz — `--dry-run` works without it).

## Install

From the project root:

```bash
pip install -e .
```

This installs the `stackfuzz` command (via the `[project.scripts]` entry point)
and bundles the wordlists as package data, so it works from anywhere once
installed.

You can also run it without installing:

```bash
python -m stackfuzz https://example.com --dry-run
```

## Usage

```bash
stackfuzz <target-url> [--dry-run] [--timeout SECONDS] [-- <extra ffuf flags>]
```

- `target` — required, must be a valid `http(s)://` URL.
- `--dry-run` — print the assembled `ffuf` command instead of running it.
- `--timeout` — HTTP timeout for the detection request (default: 10s).
- Anything after `--` is passed straight through to `ffuf` (match codes,
  threads, filters, etc.).

### Examples

Detect and print the command that would run (no `ffuf` needed):

```bash
stackfuzz https://example.com --dry-run
```

Detect and fuzz, adding your own ffuf flags:

```bash
stackfuzz https://example.com -- -mc 200,301,302,401,403 -t 40
```

## Limitation: detection is best-effort

Stack detection relies on signals a server *may* expose, and production setups
routinely hide them:

- `x-powered-by` (the strongest signal for Next.js / Express) is usually
  **stripped in production**.
- A reverse proxy or CDN (nginx, Cloudflare, ...) commonly **overrides or
  removes the `Server` header**, hiding Werkzeug/Gunicorn hints.
- Cookies may not be set on the landing page, or may be renamed.

When no signal is found, `stackfuzz` does **not** guess — it falls back to
`generic.txt`. Treat the detected stack as a hint, not a guarantee; when in
doubt, run the generic list too.

## Wordlists

This MVP ships **only its own curated wordlists** (`stackfuzz/wordlists/`) with
realistic per-stack paths. It intentionally does **not** bundle or reference
SecLists or Kali wordlist paths. To extend coverage, drop a `.txt` into
`stackfuzz/wordlists/` and map it in `TECH_TO_LISTS` in
[`stackfuzz/resolver.py`](stackfuzz/resolver.py).

## Project layout

```
stackfuzz/
  detector.py   # recon + signature rules -> detected techs
  resolver.py   # techs -> wordlists (merge + dedup when several)
  runner.py     # build / check / run the ffuf command
  cli.py        # argparse entry point
  wordlists/    # curated per-stack wordlists
```
