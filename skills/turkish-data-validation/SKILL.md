---
name: turkish-data-validation
description: Validate and format Turkish data in code — T.C. Kimlik No (TCKN, 11 digits, two checksums), Vergi Kimlik No (VKN, 10 digits, one checksum), Turkish IBANs (TR + 24 digits, ISO 13616 mod-97, bank decoded from the TCMB table), Turkish phone numbers (mobile, landline, 444 / 0850 / 0800, E.164 normalization), Turkish licence plates (province code 01-81), Turkish postal codes (5 digits, province in the first two), plus Turkish money (1.250,50 TL), dates (18.11.2026) and Turkish case conversion (istanbul -> ISTANBUL, not ISTANBUL). Use when an agent writes or validates Turkish forms, imports Turkish customer data, generates Turkish test fixtures, or formats Turkish text for display. Also use before sending any Turkish identifier to an API or storing it — a failing checksum is a typo, not a real ID.
---

# Turkish data validation — stop shipping Turkish IDs your code never checked

Every Turkish form, import job and agent-written fixture touches
the same identifiers — TCKN, VKN, IBAN, phone, plate, postal code —
and agents validate them by guessing. The guesses are wrong in
specific, repeatable ways: a TCKN "validated" by length alone
(11 digits is not enough — the last two digits are checksums);
a VKN copied from a blog post with the wrong check digit; an
IBAN with two digits transposed that no regex catches; a phone
number stored as "532..." with no country code; `"istanbul".upper()`
returning "ISTANBUL" (English rules — the Turkish form is
"İSTANBUL"); money formatted as "1,250.50 ₺" (English separators
— Turkish is "1.250,50 ₺").

This skill is the deterministic check for all of it: one
zero-dependency stdlib tool, one command per check, and the exact
rule that failed named in every rejection. It complements the
validators that already exist as libraries (ssg/TurkishId,
epigra/tckimlik, laravingo/turkiye-validator, turkish_kit) — those
are code for one framework or one data type. This is the agent
layer: a skill with the rules in prose, a CLI any agent can run,
a CSV audit for whole imports, test-data generation, and an MCP
server for any client.

## The contract

1. **Check first, with the tool — never guess.** Run the bundled
   checker (zero-dependency, Python stdlib only):

   ```bash
   python3 scripts/turkish_data_validation.py validate tckn 10000000146
   python3 scripts/turkish_data_validation.py validate iban "TR33 0006 1005 1978 6457 8413 26"
   python3 scripts/turkish_data_validation.py detect "0532 123 45 67"
   ```

   Exit codes: `0` = valid · `1` = invalid · `2` = usage error.
   `--json` gives machine-readable output for CI.

   Not sure of the type? Use `detect` — it guesses the type from
   the shape (11 digits starting with 0 is a phone with its trunk
   0, not a TCKN — TCKNs never start with 0) and then validates it.

2. **Fix the data, not the check.** A failing checksum is a typo
   in the data. Never "fix" it by editing the validator, by
   dropping the check digit, or by re-typing the number from
   memory. Go back to the source (the form, the export, the
   customer) and get the real value. If the source is gone, the
   row is invalid — say so and move on.

3. **Prove the fix.** Do not report a value as fixed after editing
   it — re-run the check until it exits 0. Quote the final
   `[VALID]` line in your report.

4. **A checksum is not an identity check.** A passing checksum
   only proves the digits are mutually consistent. It cannot prove
   the number was issued, is still active, or belongs to the person
   quoting it. Only the issuing authority can confirm that
   (Nüfus for TCKN, GİB for VKN, the bank for an IBAN). Never
   present a passing checksum as proof of identity, and never send
   a real person's ID number to a service that does not need it.

5. **Generate test data; never reuse real IDs.** Fixtures and
   examples must use `generate` output, which satisfies the real
   checksum but is arithmetic only — it does not correspond to a
   real holder:

   ```bash
   python3 scripts/turkish_data_validation.py generate tckn --seed 42
   python3 scripts/turkish_data_validation.py generate iban --seed 5
   ```

## What each check means

- **TDV-01 TCKN** — 11 digits, first digit not 0. d10 =
  ((d1+d3+d5+d7+d9) × 7 − (d2+d4+d6+d8)) mod 10; d11 = sum of the
  first 10 digits mod 10. The canonical test number is
  10000000146 (used in Turkish validator documentation).
- **TDV-02 VKN** — 10 digits, one checksum. For each position i
  (0-based): tmp = (digit + 9 − i) mod 10; v = (tmp × 2^(9−i))
  mod 9; a zero tmp contributes 0, any other zero v becomes 9;
  check = (10 − sum mod 10) mod 10. Cross-checked against the
  python-stdnum reference on 2,000 random prefixes (by the
  turkiye-mcp project). An 11-digit input is validated as a TCKN —
  individuals use their national ID as their tax ID. Published
  examples: 1234567890 and 4540536920 are valid; 0010048920 is not
  (its check digit should be 6).
- **TDV-03 IBAN** — TR + 24 digits, ISO 13616 mod-97 = 1. Decodes
  the bank code (5 digits), the reserved digit (usually 0) and the
  16-digit account part, and names the bank from the TCMB
  participant table when the code is known. An unknown bank code
  is a warning, not an error — the IBAN can still be valid.
  Example: TR33 0006 1005 1978 6457 8413 26 (bank code 00061, not
  in the TCMB table — valid, bank unknown).
- **TDV-04 phone** — mobile (5xx, 10 digits), landline (0 +
  3-digit area code + 7 digits), 444 xxxx, 0850/0800, short
  numbers (112, 155, 156, 110). Accepts +90, 0090, 90 and trunk-0
  forms; normalizes to E.164 (+905321234567) and formats as
  (0532) 123 45 67. The landline city is named only for area codes
  in the verified list (30 largest cities); any other area code
  gives a warning, never an error.
- **TDV-05 plate** — province code 01–81 + 1–3 letters (A–Z) +
  2–4 digits; 3-letter plates have 2–3 digits. Resolves the
  province name (34 = İstanbul, 06 = Ankara, 35 = İzmir).
  Turkish plates use A–Z only — Ç/Ğ/İ/Ö/Ş/Ü are rejected.
- **TDV-06 postal** — 5 digits; the first two are the province
  code 01–81 (34000 = İstanbul, 06000 = Ankara, 81000 = Düzce).

## Batch audit

Validate a whole import before it lands:

```bash
python3 scripts/turkish_data_validation.py audit customers.csv --column tckn
python3 scripts/turkish_data_validation.py audit customers.csv --column phone --type phone --json
```

`audit` reports `N rows, M valid, K invalid` plus one line per
invalid row with the exact rule it failed. Omit `--type` to
auto-detect the type of each cell. Exit 1 when any row is invalid.

## Formatters (the traps)

```bash
python3 scripts/turkish_data_validation.py format money 1250.5   # 1.250,50 ₺
python3 scripts/turkish_data_validation.py format date 2026-11-18  # 18.11.2026
python3 scripts/turkish_data_validation.py format upper istanbul   # İSTANBUL
python3 scripts/turkish_data_validation.py format lower İSTANBUL   # istanbul
python3 scripts/turkish_data_validation.py format iban TR330006100519786457841326
python3 scripts/turkish_data_validation.py format phone 5321234567  # (0532) 123 45 67
```

Turkish case is the silent one: Python's `"i".upper()` is `"I"`
and `"I".lower()` is `"i"` — both wrong in Turkish. Use
`tr_upper` / `tr_lower` (i → İ, ı → I, I → ı, İ → i) for any
user-facing Turkish text, and for `.upper()` / `.lower()` on
identifiers that pass through Turkish text.

## MCP server

`mcp-server/turkish_data_validation_mcp_server.py` exposes the
same capability over stdio JSON-RPC: `validate_turkish_data`,
`detect_turkish_data`, `format_turkish_data`,
`generate_turkish_test_data`, `audit_turkish_csv` and
`list_turkish_checks`. See `tests/test_mcp_server.py` for a full
lifecycle test.

## Limits — say them in every report

- Checksums prove consistency, not issuance (see rule 4).
- The VKN check catches typos; it cannot tell a company VKN from
  a mistyped one, and individuals' tax IDs are their TCKN.
- The bank table follows TCMB's 2026 participant list; new banks
  and payment institutions appear — an unknown bank code is a
  warning, and the table needs a periodic refresh.
- The landline area-code list covers the 30 largest cities only.
- Plate validation checks the format and the province code, not
  whether the plate is registered to a vehicle.
