# turkish-data-validation

**Validate and format Turkish data in code — the agent layer Turkish validators were missing.**

Every Turkish form, import job and agent-written fixture touches
the same identifiers — TCKN, VKN, IBAN, phone, plate, postal code —
and agents validate them by guessing. The guesses are wrong in
specific, repeatable ways: a TCKN "validated" by length alone
(11 digits is not enough — the last two digits are checksums);
a VKN copied from a blog post with the wrong check digit; an IBAN
with two digits transposed that no regex catches; a phone number
stored as "532..." with no country code; `"istanbul".upper()`
returning "ISTANBUL" (English rules — the Turkish form is
"İSTANBUL"); money formatted as "1,250.50 ₺" (English separators
— Turkish is "1.250,50 ₺").

## What it checks

| Code | Check | Example |
|------|-------|---------|
| TDV-01 | TCKN (11 digits, two checksums) | 10000000146 valid; 10000000145 fails the 11th digit |
| TDV-02 | VKN (10 digits, one checksum) | 1234567890 valid; 0010048920 fails (check should be 6) |
| TDV-03 | Turkish IBAN (TR + 24 digits, mod-97) | TR33 0006 1005 1978 6457 8413 26 valid; TR32… fails mod-97 |
| TDV-04 | Turkish phone (mobile / landline / 444 / 0850 / 0800) | +90 532 123 45 67 → +905321234567, (0532) 123 45 67 |
| TDV-05 | Licence plate (province 01–81) | 34 AB 123 → İstanbul; 99 AB 123 invalid |
| TDV-06 | Postal code (5 digits, province in first two) | 34000 → İstanbul; 99000 invalid |

Formatters: money (`1250.5` → `1.250,50 ₺`), dates
(`2026-11-18` → `18.11.2026`), Turkish case (`istanbul` →
`İSTANBUL`).

## Before / after

```text
$ python3 scripts/turkish_data_validation.py validate tckn 10000000145
[INVALID] tckn: 11th digit checksum mismatch (expected 6, got 5).

$ python3 scripts/turkish_data_validation.py audit customers.csv --column tckn
customers.csv: 5 rows, 3 valid, 2 invalid.
  row 4: '10000000145' (tckn): 11th digit checksum mismatch (expected 6, got 5).
  row 6: '1000000014' (tckn): TCKN must be exactly 11 digits (got 10).
```

## Honest framing: what already exists

Validators for Turkish data exist — as libraries, for one
framework or one data type at a time:

- [ssg/TurkishId](https://github.com/ssg/TurkishId) (★88),
  [epigra/tckimlik](https://github.com/epigra/tckimlik) (★70),
  [krmbzds/turkish_id](https://github.com/krmbzds/turkish_id)
  (★20) — TCKN only.
- [laravingo/turkiye-validator](https://github.com/laravingo/turkiye-validator)
  (★16) — TCKN, VKN, IBAN and landlines, but Laravel-only.
- [turkish_kit](https://pub.dev/documentation/turkish_kit/latest/)
  and `turkish_validators` — Dart/Flutter only.
- [celaldrg/turkiye-mcp](https://github.com/celaldrg/turkiye-mcp)
  (★0) — a general Türkiye MCP server (17 tools: exchange rates,
  earthquakes, holidays, prayer times, weather…) where
  IBAN/TCKN/VKN validation is 3 of 17 tools, with no agent skill,
  no CLI, no phone/plate/postal checks, no formatting and no
  batch audit.

None of them is an agent skill: no SKILL.md with the rules in
prose, no deterministic stdlib CLI an agent can run anywhere, no
CSV audit for whole imports, no test-data generation, no Cursor
rule. This repo is that layer — it complements the libraries, it
does not replace them. The VKN algorithm here was cross-checked
against python-stdnum's reference behaviour (via turkiye-mcp's
2,000-prefix check), and the 81-province table was verified
against the same project's province list (all 81 names match).

## Install

**Claude Code / Claude.ai** — copy the skill directory, or upload
the `dist/turkish-data-validation-skill.zip`:

```bash
cp -r skills/turkish-data-validation ~/.claude/skills/
```

**Cursor** — copy `cursor/turkish-data-validation.mdc` into your
project's `.cursor/rules/` (see `cursor/README.md` for Windsurf,
Cline and Continue).

**MCP (any client)** — the stdio server in `mcp-server/` exposes
`validate_turkish_data`, `detect_turkish_data`,
`format_turkish_data`, `generate_turkish_test_data`,
`audit_turkish_csv` and `list_turkish_checks`:

```json
{
  "mcpServers": {
    "turkish-data-validation": {
      "command": "python3",
      "args": ["mcp-server/turkish_data_validation_mcp_server.py"]
    }
  }
}
```

**Direct use** — no install, no dependencies (Python 3.9+ stdlib
only):

```bash
python3 skills/turkish-data-validation/scripts/turkish_data_validation.py validate tckn 10000000146
python3 skills/turkish-data-validation/scripts/turkish_data_validation.py detect "0532 123 45 67"
python3 skills/turkish-data-validation/scripts/turkish_data_validation.py generate tckn --seed 42
python3 skills/turkish-data-validation/scripts/turkish_data_validation.py audit customers.csv --column tckn
```

## Verification (no statistical claims without a run)

- **92 tests pass** (`pytest tests/`): every check code with
  valid/invalid vectors, the published examples (TCKN
  10000000146, VKN 1234567890 / 4540536920, IBAN
  TR33 0006 1005 1978 6457 8413 26), generator round-trips,
  formatters (including the Turkish-case trap), `detect`
  disambiguation (an 11-digit number starting with 0 is a phone,
  not a TCKN), CLI exit codes, JSON output, the CSV audit
  fixture, and MCP stdio end-to-end.
- The VKN checksum was verified against published vectors — the
  first version of the algorithm failed 1234567890 and the test
  vectors caught it before release (see
  `skills/turkish-data-validation/references/validation-rules.md`).
- The 81-province table was verified name-by-name against an
  independent source (all 81 match).

## What it does not do

- It does not prove identity. A passing checksum only proves the
  digits are mutually consistent — never that the number was
  issued or belongs to anyone. Only the issuing authority can
  confirm that.
- It does not know districts or streets (postal codes stop at the
  province) — that needs the PTT address dataset.
- It does not map phone prefixes to operators — number
  portability made those mappings unreliable years ago.
- It does not validate MERSIS numbers or SGK numbers (roadmap).
- The bank table follows TCMB's 2026 participant list; an unknown
  bank code is a warning, and the table needs a periodic refresh.

See `skills/turkish-data-validation/references/validation-rules.md`
for the full reasoning, and
`skills/turkish-data-validation/references/examples.md` for worked
before/after cases.

## Roadmap

- MERSIS (16-digit company registry number) validation.
- SGK (social security) number validation.
- District-level postal-code lookup (PTT dataset, with its source
  stated).
- CI action: fail a PR when a Turkish fixture introduces an
  invalid identifier.
- Periodic refresh check for the TCMB bank table.

## License

MIT. Persian version: [README-fa.md](README-fa.md).
