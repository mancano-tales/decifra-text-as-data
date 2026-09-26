# Security Policy

Decifra is pre-1.0 software under active, single-repository development.
There is no formal support matrix yet — only the `main` branch is
maintained, and security fixes land there directly.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository
(the "Report a vulnerability" button under the repo's **Security** tab)
rather than opening a public issue. This keeps the report private between
you and the maintainer until a fix is available.

If private reporting isn't available or convenient, open an issue with
`[security]` in the title and minimal detail (enough to confirm receipt,
not full exploit details), and the maintainer will follow up to arrange a
private channel.

Please do not publicly disclose a vulnerability before a fix has been
released.

## What's in scope

- The backend (`src/text_as_data/`) and its API (`app.py`), including
  handling of uploaded corpus files (CSV/XLSX/pasted text) and generated
  exports (CSV/XLSX/JSON).
- The frontend (`frontend/`).
- Anything that could expose an LLM provider API key, corpus data, or
  another user's data to an unintended party.

## What's out of scope

- The LLM providers themselves (Anthropic, OpenAI, or any CLI Decifra shells
  out to) — report those upstream.
- Findings that require local admin/filesystem access to the machine
  running Decifra — this is a local-first tool with no remote deployment in
  its current design (see the architecture section of `docs/PRODUCT_BRIEF.md`).

## Response expectations

This is a solo/small-team research project, not a funded security
program — there is no SLA. Reports will get a best-effort acknowledgment
and a fix timeline once triaged, prioritized by real-world impact.
