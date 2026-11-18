# Worked examples — before / after

All numbers below are published examples or generated test values
(`generate` output). None belongs to a real person or company.

## 1. A TCKN with a typo

Before — an agent copies an ID from a form:

```text
TCKN: 10000000145
```

```bash
$ python3 scripts/turkish_data_validation.py validate tckn 10000000145
[INVALID] tckn: 11th digit checksum mismatch (expected 6, got 5).
```

The 11th digit is a checksum over the first ten — 5 cannot be
right if the first ten digits are right. Go back to the source;
do not guess which digit is wrong.

After — the source confirms the real number:

```bash
$ python3 scripts/turkish_data_validation.py validate tckn 10000000146
[VALID] tckn: OK
```

## 2. A VKN from a blog post

```bash
$ python3 scripts/turkish_data_validation.py validate vkn 0010048920
[INVALID] vkn: Check digit mismatch (expected 6, got 0).
```

`0010048920` circulates as an example in some test suites, but
its check digit is wrong. The valid published examples are
`1234567890` and `4540536920`.

## 3. An IBAN with two digits transposed

```bash
$ python3 scripts/turkish_data_validation.py validate iban "TR33 0006 1005 1978 6457 8413 26"
[VALID] iban: OK
    formatted: TR33 0006 1005 1978 6457 8413 26
    bank_code: 00061
    bank: None
    warning: Bank code 00061 is not in the TCMB participant table — the IBAN can still be valid.
```

```bash
$ python3 scripts/turkish_data_validation.py validate iban "TR32 0006 1005 1978 6457 8413 26"
[INVALID] iban: Checksum (mod-97) failed. Check for a typo.
```

One digit changed (33 → 32) and mod-97 catches it. A regex
would have passed both. The unknown bank code in the valid one
is a warning, not an error.

## 4. A phone number in five spellings

All of these are the same number — normalize before storing:

```bash
$ python3 scripts/turkish_data_validation.py validate phone "+90 532 123 45 67"
[VALID] phone: OK
    normalized: 05321234567
    formatted: (0532) 123 45 67
    e164: +905321234567
```

`0532 123 45 67`, `00905321234567`, `905321234567` and
`5321234567` all validate to the same E.164 form. Storing the
raw string means the same customer matches four times — or never.

## 5. A CSV import, audited before it lands

`customers.csv`:

```csv
name,tckn
Ayşe Yılmaz,10000000146
Mehmet Demir,20433218148
Zeynep Kaya,10000000145
Emre Şahin,62601815964
Elif Çelik,1000000014
```

```bash
$ python3 scripts/turkish_data_validation.py audit customers.csv --column tckn
customers.csv: 5 rows, 3 valid, 2 invalid.
  row 4: '10000000145' (tckn): 11th digit checksum mismatch (expected 6, got 5).
  row 6: '1000000014' (tckn): TCKN must be exactly 11 digits (got 10).
```

Two rows go back to the source. The other three are proven valid.

## 6. The Turkish-case trap

```python
>>> "istanbul".upper()
'ISTANBUL'          # English rules — wrong in Turkish
>>> tr_upper("istanbul")
'İSTANBUL'          # correct
>>> "IĞDIR".lower()
'ıgdır'             # English lower() gives 'ığdır' by luck here,
                    # but "ISTANBUL".lower() gives 'istanbul' — wrong:
                    # the I must become 'ı', so it is 'ıstanbul'
```

```bash
$ python3 scripts/turkish_data_validation.py format upper istanbul
İSTANBUL
$ python3 scripts/turkish_data_validation.py format lower İSTANBUL
istanbul
```

## 7. Test fixtures without real IDs

```bash
$ python3 scripts/turkish_data_validation.py generate tckn --seed 42
20433218148
$ python3 scripts/turkish_data_validation.py generate vkn --seed 42
1043321815
$ python3 scripts/turkish_data_validation.py generate iban --seed 5
TR62 0006 2094 5807 3021 5736 81
```

Generated values satisfy the real checksums, so tests exercise
the real code paths — but they are arithmetic, not registry
entries, and must never be presented as real IDs.
