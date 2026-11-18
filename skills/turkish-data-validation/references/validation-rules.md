# Validation rules — why each check exists

## TDV-01 — T.C. Kimlik No (TCKN)

The Turkish national ID is 11 digits with two check digits. The
algorithm is published by the Nüfus (civil registry) and repeated
in every Turkish validator:

- d1 is never 0.
- d10 = ((d1 + d3 + d5 + d7 + d9) × 7 − (d2 + d4 + d6 + d8)) mod 10
- d11 = (d1 + d2 + … + d10) mod 10

Worked example — 10000000146 (the number used in Turkish
validator documentation):

- odd positions (1,3,5,7,9): 1 + 0 + 0 + 0 + 1 = 2; × 7 = 14
- even positions (2,4,6,8): 0
- d10 = (14 − 0) mod 10 = 4 ✓
- d11 = (1 + 0 + 0 + 0 + 0 + 0 + 0 + 0 + 1 + 4) mod 10 = 6 ✓

Why length alone is not enough: any 11-digit string passes a
length check, but a single transposed digit breaks one of the two
checksums — that is the whole point. Agents that "validate" by
length alone pass typos through to the database.

## TDV-02 — Vergi Kimlik No (VKN)

The company tax ID is 10 digits with one check digit. The
algorithm, as implemented in python-stdnum (`stdnum.tr.vkn`) and
cross-checked by the turkiye-mcp project on 2,000 random prefixes:

- For each position i (0-based, first 9 digits):
  tmp = (digit + 9 − i) mod 10
  v = (tmp × 2^(9−i)) mod 9
  a tmp of 0 contributes 0; any other v of 0 becomes 9.
- check = (10 − sum mod 10) mod 10; it must equal the 10th digit.

Worked example — 1234567890:

- every tmp is 0 (digit + 9 − i is 10 for each position), so every
  v is 0, sum is 0, check is (10 − 0) mod 10 = 0 ✓

The subtle part is the zero handling: an early version of this
skill's own algorithm replaced tmp = 0 with 10 before the
multiplication, which made 1234567890 fail. The published test
vectors caught it (1234567890 and 4540536920 are valid;
0010048920 is not — its check digit should be 6). Lesson: never
ship a checksum from memory; verify it against published vectors
and a reference implementation.

Individuals do not have a VKN: their tax ID *is* their TCKN.
An 11-digit input to the VKN check is therefore validated as a
TCKN, not rejected.

## TDV-03 — Turkish IBAN

TR + 2 check digits + 22-digit BBAN (5-digit bank code + 1
reserved digit + 16-digit account number) = 26 characters.
Validated by ISO 13616 mod-97: move the first four characters
to the end, convert letters (A=10 … Z=35) to digits, and the
result mod 97 must be 1.

Structure of TR33 0006 1005 1978 6457 8413 26:

- check digits: 33
- bank code: 00061 (not in the TCMB participant table — valid,
  bank unknown)
- reserved digit: 0
- account part: 0519786457841326

The bank table is TCMB's "Ödeme Sistemleri Katılımcıları (2026)"
and FAST participant list. Keys are the 5-digit IBAN form of the
EFT code: Garanti BBVA's EFT code 62 is `00062` inside an IBAN,
Ziraat's 10 is `00010`, İş Bankası's 64 is `00064`. An unknown
bank code is a warning, never an error — new banks and payment
institutions join, and a valid IBAN must not fail because the
table is a month out of date.

## TDV-04 — Turkish phone numbers

Accepted forms, all normalized to E.164 (`+90...`):

| Form | Example | Normalized |
|------|---------|------------|
| mobile, with trunk 0 | 0532 123 45 67 | +905321234567 |
| mobile, international | +90 532 123 45 67 | +905321234567 |
| mobile, 0090 | 00905321234567 | +905321234567 |
| mobile, bare | 5321234567 | +905321234567 |
| landline | 0212 123 45 67 | +902121234567 |
| 444 service | 444 1 234 | +904441234 |
| 0850 / 0800 | 0850 305 12 34 | +908503051234 |
| short numbers | 112, 155, 156, 110 | as given |

Rules: mobile numbers are 10 digits starting with 5 (after
stripping +90 / 0090 / 90 / 0). Landlines are 0 + 3-digit area
code + 7 digits; the city is named only for the 30 area codes in
the verified list (212/216 İstanbul, 312 Ankara, 232 İzmir, 224
Bursa, 322 Adana, 332 Konya, 242 Antalya, 222 Eskişehir, 324
Mersin, 352 Kayseri, 362 Samsun, 342 Gaziantep, 258 Denizli,
236 Manisa, 462 Trabzon, 412 Diyarbakır, 422 Malatya, 432 Van,
442 Erzurum, 452 Ordu, 372 Zonguldak, 346 Sivas, 356 Tokat,
344 Kahramanmaraş, 326 Hatay, 328 Osmaniye, 318 Kırıkkale,
386 Kırşehir, 388 Niğde). Any other area code is a warning, not
an error — the list is deliberately conservative.

Operator prefixes (532 = Turkcell, 505 = Vodafone, etc.) are
NOT validated: number portability has made them unreliable for
years. Any source that maps prefixes to operators is stale.

## TDV-05 — Turkish licence plates

Format: 2-digit province code (01–81) + 1–3 letters (A–Z) +
2–4 digits. 3-letter plates have 2–3 digits; 1–2-letter plates
have 2–4 digits. Examples: `34 AB 123`, `34 ABC 12`,
`06 AA 1234`, `81 AZ 999`.

The province table is the official traffic-code list (01 Adana …
81 Düzce), cross-checked 2026-11-18 against the province list in
celaldrg/turkiye-mcp (source: turkey-neighbourhoods v4.0.3) —
all 81 names match.

Turkish plates use A–Z only. Ç/Ğ/İ/Ö/Ş/Ü never appear on a
plate; input containing them is rejected with that reason, not
silently normalized.

## TDV-06 — Turkish postal codes

5 digits; the first two are the province code (01–81), so
34000–34999 is İstanbul, 06000–06999 Ankara, 81000–81999 Düzce.
The check validates the shape and the province — it does not
know districts or streets, which need the PTT address dataset.

## Formatters

- **Money:** Turkish format is `1.250,50 ₺` — dot for thousands,
  comma for decimals. English `1,250.50` is wrong in Turkish text.
- **Dates:** Turkish format is `18.11.2026` (DD.MM.YYYY).
- **Case:** i → İ, ı → I, I → ı, İ → i. Python's default
  `"i".upper()` gives `"I"` and `"I".lower()` gives `"i"` — both
  wrong in Turkish. The classic visible failure:
  `"istanbul".upper()` → `"ISTANBUL"` (English) instead of
  `"İSTANBUL"` (Turkish).
