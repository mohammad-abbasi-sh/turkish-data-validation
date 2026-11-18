#!/usr/bin/env python3
"""turkish-data-validation — deterministic validation and formatting
for Turkish data in code.

Zero-dependency (Python standard library only). Validates the
identifiers every Turkish form, import job and agent-written code
touches, with the exact rule that failed named for each rejection:

    TDV-01  T.C. Kimlik No (TCKN, 11 digits, two checksums)
    TDV-02  Vergi Kimlik No (VKN, 10 digits, one checksum)
    TDV-03  Turkish IBAN (TR + 24 digits, ISO 13616 mod-97)
    TDV-04  Turkish phone numbers (mobile, landline, 444 / 0850 / 0800)
    TDV-05  Turkish licence plates (province code 01-81 + letters/digits)
    TDV-06  Turkish postal codes (5 digits, province in the first two)

Plus the formatting helpers agents get wrong without a reference:
Turkish money (1.234,56 TL), Turkish dates (18.11.2026), and
Turkish case conversion: "istanbul".upper() is "İSTANBUL" in
Turkish (dotted capital I) — English rules give "ISTANBUL"
(dotless I), which is wrong in Turkish. The same trap bites
every "I".lower() call: it must be "ı", not "i".

A checksum only proves the digits are mutually consistent. It
cannot prove the number was issued, is still active, or belongs
to the person quoting it. Only the issuing authority can confirm
that. Never present a passing checksum as proof of identity,
and never send a real person's ID number to a service that does
not need it.

Usage:
    tdv.py validate tckn 10000000146
    tdv.py validate vkn 1234567890
    tdv.py validate iban "TR33 0006 1005 1978 6457 8413 26"
    tdv.py validate phone "+90 532 123 45 67"
    tdv.py validate plate "34 AB 123"
    tdv.py validate postal 34000
    tdv.py detect "0532 123 45 67"
    tdv.py format iban TR330006100519786457841326
    tdv.py format phone 5321234567
    tdv.py format money 1250.5
    tdv.py format upper istanbul
    tdv.py generate tckn [--seed 42]
    tdv.py audit customers.csv --column tckn [--type tckn] [--json]

Exit codes: 0 = valid / success, 1 = invalid / findings,
2 = usage error or unreadable file.
"""
import argparse
import csv
import json
import random
import re
import sys
from datetime import date

VERSION = "0.1.0"

# ---------------------------------------------------------------- tables

# Official province (il) traffic codes 01-81. Cross-checked 2026-11-18
# against the province list in celaldrg/turkiye-mcp (source:
# turkey-neighbourhoods v4.0.3) — all 81 names match.
PROVINCES = {
    "01": "Adana", "02": "Adıyaman", "03": "Afyonkarahisar",
    "04": "Ağrı", "05": "Amasya", "06": "Ankara", "07": "Antalya",
    "08": "Artvin", "09": "Aydın", "10": "Balıkesir",
    "11": "Bilecik", "12": "Bingöl", "13": "Bitlis", "14": "Bolu",
    "15": "Burdur", "16": "Bursa", "17": "Çanakkale",
    "18": "Çankırı", "19": "Çorum", "20": "Denizli",
    "21": "Diyarbakır", "22": "Edirne", "23": "Elazığ",
    "24": "Erzincan", "25": "Erzurum", "26": "Eskişehir",
    "27": "Gaziantep", "28": "Giresun", "29": "Gümüşhane",
    "30": "Hakkari", "31": "Hatay", "32": "Isparta", "33": "Mersin",
    "34": "İstanbul", "35": "İzmir", "36": "Kars",
    "37": "Kastamonu", "38": "Kayseri", "39": "Kırklareli",
    "40": "Kırşehir", "41": "Kocaeli", "42": "Konya",
    "43": "Kütahya", "44": "Malatya", "45": "Manisa",
    "46": "Kahramanmaraş", "47": "Mardin", "48": "Muğla",
    "49": "Muş", "50": "Nevşehir", "51": "Niğde", "52": "Ordu",
    "53": "Rize", "54": "Sakarya", "55": "Samsun", "56": "Siirt",
    "57": "Sinop", "58": "Sivas", "59": "Tekirdağ", "60": "Tokat",
    "61": "Trabzon", "62": "Tunceli", "63": "Şanlıurfa",
    "64": "Uşak", "65": "Van", "66": "Yozgat", "67": "Zonguldak",
    "68": "Aksaray", "69": "Bayburt", "70": "Karaman",
    "71": "Kırıkkale", "72": "Batman", "73": "Şırnak",
    "74": "Bartın", "75": "Ardahan", "76": "Iğdır", "77": "Yalova",
    "78": "Karabük", "79": "Kilis", "80": "Osmaniye",
    "81": "Düzce",
}

# Bank EFT codes (the 5 digits after TR + check digits in an IBAN).
# Public registry data, source: TCMB "Ödeme Sistemleri Katılımcıları
# (2026)" and the FAST participant list, as published by TCMB.
# Keys are the 5-digit IBAN form of the EFT code (e.g. Garanti
# BBVA's EFT code 62 is "00062" inside an IBAN).
# An IBAN whose bank code is not in this table is still valid if
# mod-97 passes — the bank is then reported as unknown, not as an
# error.
BANKS = {
    "00001": "T.C. Merkez Bankası",
    "00004": "İller Bankası A.Ş.",
    "00010": "T.C. Ziraat Bankası A.Ş.",
    "00012": "Türkiye Halk Bankası A.Ş.",
    "00014": "Türkiye Sınai Kalkınma Bankası A.Ş.",
    "00015": "Türkiye Vakıflar Bankası T.A.O.",
    "00016": "Türk Eximbank",
    "00017": "Türkiye Kalkınma ve Yatırım Bankası A.Ş.",
    "00029": "Birleşik Fon Bankası A.Ş.",
    "00032": "Türk Ekonomi Bankası A.Ş. (TEB)",
    "00046": "Akbank T.A.Ş.",
    "00059": "Şekerbank T.A.Ş.",
    "00060": "Türk Ticaret Bankası A.Ş.",
    "00062": "Türkiye Garanti Bankası A.Ş. (Garanti BBVA)",
    "00064": "Türkiye İş Bankası A.Ş.",
    "00067": "Yapı ve Kredi Bankası A.Ş.",
    "00091": "Arap Türk Bankası A.Ş.",
    "00092": "Citibank A.Ş.",
    "00096": "Freedom Bank A.Ş. (formerly Turkish Bank A.Ş.)",
    "00098": "JPMorgan Chase Bank N.A.",
    "00099": "ING Bank A.Ş.",
    "00103": "Fibabanka A.Ş.",
    "00108": "Turkland Bank A.Ş.",
    "00109": "ICBC Turkey Bank A.Ş.",
    "00111": "QNB Bank A.Ş. (QNB Finansbank)",
    "00115": "Deutsche Bank A.Ş.",
    "00116": "Pasha Yatırım Bankası A.Ş.",
    "00121": "Standard Chartered Yatırım Bankası Türk A.Ş.",
    "00122": "Société Générale (SA)",
    "00123": "HSBC Bank A.Ş.",
    "00124": "Alternatifbank A.Ş.",
    "00125": "Burgan Bank A.Ş.",
    "00129": "Bank of America Yatırım Bank A.Ş.",
    "00132": "İstanbul Takas ve Saklama Bankası A.Ş. (Takasbank)",
    "00134": "Denizbank A.Ş.",
    "00135": "Anadolubank A.Ş.",
    "00137": "Hepsi Bank A.Ş. (formerly Rabobank A.Ş.)",
    "00138": "Diler Yatırım Bankası A.Ş.",
    "00139": "GSD Yatırım Bankası A.Ş.",
    "00141": "Nurol Yatırım Bankası A.Ş.",
    "00142": "Bankpozitif Kredi ve Kalkınma Bankası A.Ş.",
    "00143": "Aktif Yatırım Bankası A.Ş.",
    "00146": "Odea Bank A.Ş.",
    "00147": "MUFG Bank Turkey A.Ş.",
    "00148": "Intesa Sanpaolo S.p.A.",
    "00149": "Bank of China Turkey A.Ş.",
    "00151": "D Yatırım Bankası A.Ş.",
    "00152": "Destek Yatırım Bankası A.Ş.",
    "00153": "Misyon Yatırım Bankası A.Ş.",
    "00154": "Tera Yatırım Bankası A.Ş.",
    "00155": "Q Yatırım Bankası A.Ş.",
    "00156": "Hedef Yatırım Bankası A.Ş.",
    "00157": "Enpara Bank A.Ş.",
    "00158": "Colendi Bank A.Ş.",
    "00159": "Fups Bank A.Ş.",
    "00160": "Ziraat Dinamik Banka A.Ş.",
    "00161": "Aytemiz Yatırım Bankası A.Ş.",
    "00203": "Albaraka Türk Katılım Bankası A.Ş.",
    "00205": "Kuveyt Türk Katılım Bankası A.Ş.",
    "00206": "Türkiye Finans Katılım Bankası A.Ş.",
    "00209": "Ziraat Katılım Bankası A.Ş.",
    "00210": "Vakıf Katılım Bankası A.Ş.",
    "00211": "Türkiye Emlak Katılım Bankası A.Ş.",
    "00212": "Hayat Finans Katılım Bankası A.Ş.",
    "00213": "T.O.M. Katılım Bankası A.Ş.",
    "00214": "Dünya Katılım Bankası A.Ş.",
    "00215": "Adil Katılım Bankası A.Ş.",
    "00216": "İktisat Katılım Bankası A.Ş.",
    "00806": "Merkezi Kayıt Kuruluşu A.Ş.",
    "00807": "Posta ve Telgraf Teşkilatı A.Ş. (PTT)",
    "00825": "Moka United Ödeme Hizmetleri ve Elektronik Para Kuruluşu A.Ş.",
    "00827": "Türk Elektronik Para A.Ş.",
    "00828": "Belbim Elektronik Para ve Ödeme Hizmetleri A.Ş.",
    "00829": "Papara Elektronik Para A.Ş.",
    "00838": "Sipay Elektronik Para ve Ödeme Hizmetleri A.Ş.",
    "00850": "BPN Ödeme ve Elektronik Para Hizmetleri A.Ş.",
    "00864": "İyzi Ödeme ve Elektronik Para Hizmetleri A.Ş. (iyzico)",
    "00869": "Turkcell Ödeme ve Elektronik Para Hizmetleri A.Ş. (Paycell)",
    "00890": "Lydians Elektronik Para ve Ödeme Hizmetleri A.Ş.",
    "00894": "Ahlatcı Ödeme ve Elektronik Para Hizmetleri A.Ş.",
    "00911": "AS Ödeme Hizmetleri ve Elektronik Para A.Ş.",
}

# Landline area codes verified for the largest cities. Any other
# 3-digit area code is reported as "valid format, area not in the
# verified list" (a warning), never as an error — the list below
# is deliberately conservative.
AREA_CODES = {
    "212": "İstanbul (Avrupa)", "216": "İstanbul (Anadolu)",
    "312": "Ankara", "232": "İzmir", "224": "Bursa",
    "322": "Adana", "332": "Konya", "242": "Antalya",
    "222": "Eskişehir", "324": "Mersin", "352": "Kayseri",
    "362": "Samsun", "342": "Gaziantep", "258": "Denizli",
    "236": "Manisa", "462": "Trabzon", "412": "Diyarbakır",
    "422": "Malatya", "432": "Van", "442": "Erzurum",
    "452": "Ordu", "372": "Zonguldak", "346": "Sivas",
    "356": "Tokat", "344": "Kahramanmaraş", "326": "Hatay",
    "328": "Osmaniye", "318": "Kırıkkale", "386": "Kırşehir",
    "388": "Niğde",
}

# ---------------------------------------------------------------- helpers


def _result(kind, valid, reason=None, detail=None, warnings=None):
    return {
        "kind": kind,
        "valid": valid,
        "reason": reason,
        "detail": detail or {},
        "warnings": warnings or [],
    }


def _digits_only(value):
    """Strip spaces and dashes from an identifier."""
    return re.sub(r"[\s\-]", "", str(value))


def tr_lower(text):
    """Turkish-aware lowercase: I -> ı, İ -> i (not i / I)."""
    out = []
    for ch in str(text):
        if ch == "I":
            out.append("ı")
        elif ch == "İ":
            out.append("i")
        else:
            out.append(ch.lower())
    return "".join(out)


def tr_upper(text):
    """Turkish-aware uppercase: i -> İ, ı -> I."""
    out = []
    for ch in str(text):
        if ch == "i":
            out.append("İ")
        elif ch == "ı":
            out.append("I")
        else:
            out.append(ch.upper())
    return "".join(out)


# ---------------------------------------------------------------- TDV-01 TCKN


def tckn_check_digits(first9):
    """Return the two TCKN check digits for the first 9 digits.

    d10 = ((d1+d3+d5+d7+d9) * 7 - (d2+d4+d6+d8)) mod 10
    d11 = (d1+...+d10) mod 10
    """
    d = [int(c) for c in first9]
    odd = d[0] + d[2] + d[4] + d[6] + d[8]
    even = d[1] + d[3] + d[5] + d[7]
    d10 = ((odd * 7) - even) % 10
    d11 = (sum(d) + d10) % 10
    return d10, d11


def validate_tckn(value):
    s = _digits_only(value)
    if not s.isdigit():
        return _result("tckn", False,
                       "TCKN must contain only digits (got %r)." % value)
    if len(s) != 11:
        return _result("tckn", False,
                       "TCKN must be exactly 11 digits (got %d)." % len(s))
    d = [int(c) for c in s]
    if d[0] == 0:
        return _result("tckn", False,
                       "TCKN cannot start with 0.")
    d10, d11 = tckn_check_digits(s[:9])
    if d10 != d[9]:
        return _result(
            "tckn", False,
            "10th digit checksum mismatch (expected %d, got %d)."
            % (d10, d[9]),
            {"expected_d10": d10, "given_d10": d[9]})
    if d11 != d[10]:
        return _result(
            "tckn", False,
            "11th digit checksum mismatch (expected %d, got %d)."
            % (d11, d[10]),
            {"expected_d11": d11, "given_d11": d[10]})
    return _result("tckn", True, None,
                   {"normalized": s},
                   ["Checksum is valid. This does not confirm the ID is "
                    "registered to a real person."])


def generate_tckn(seed=None):
    """A valid synthetic TCKN for tests and fixtures.

    Random digits run through the real checksum — arithmetic only,
    not drawn from any register, and it does not correspond to a
    real holder. Never use generated numbers as real IDs.
    """
    rng = random.Random(seed)
    first9 = str(rng.randint(1, 9)) + "".join(
        str(rng.randint(0, 9)) for _ in range(8))
    d10, d11 = tckn_check_digits(first9)
    return first9 + str(d10) + str(d11)


# ---------------------------------------------------------------- TDV-02 VKN


def vkn_check_digit(first9):
    """Return the VKN check digit for the first 9 digits.

    For each position i (0-based): tmp = (d[i] + 9 - i) mod 10;
    v = (tmp * 2^(9-i)) mod 9; a zero tmp contributes 0, any other
    zero v becomes 9. check = (10 - sum mod 10) mod 10.
    Cross-checked against the python-stdnum reference behaviour
    (2,000 random prefixes) by the turkiye-mcp project.
    """
    total = 0
    for i in range(9):
        tmp = (int(first9[i]) + 9 - i) % 10
        v = (tmp * (2 ** (9 - i))) % 9
        if tmp != 0 and v == 0:
            v = 9
        total += v
    return (10 - (total % 10)) % 10


def validate_vkn(value):
    s = _digits_only(value)
    if len(s) == 11 and s.isdigit():
        # Individuals use their 11-digit T.C. Kimlik No as tax ID.
        res = validate_tckn(s)
        res["kind"] = "vkn-as-tckn"
        res["detail"]["note"] = ("11-digit input: validated as TCKN, "
                                 "which individuals use as their tax ID.")
        return res
    if not s.isdigit():
        return _result("vkn", False,
                       "VKN must contain only digits (got %r)." % value)
    if len(s) != 10:
        return _result("vkn", False,
                       "VKN must be exactly 10 digits (or an 11-digit "
                       "TCKN for individuals) (got %d)." % len(s))
    expected = vkn_check_digit(s[:9])
    if expected != int(s[9]):
        return _result(
            "vkn", False,
            "Check digit mismatch (expected %d, got %s)."
            % (expected, s[9]),
            {"expected_check": expected, "given_check": int(s[9])})
    return _result("vkn", True, None,
                   {"normalized": s},
                   ["Checksum is valid. This does not confirm the tax ID "
                    "is registered."])


def generate_vkn(seed=None):
    """A valid synthetic VKN for tests and fixtures (see generate_tckn)."""
    rng = random.Random(seed)
    first9 = "".join(str(rng.randint(0, 9)) for _ in range(9))
    return first9 + str(vkn_check_digit(first9))


# ---------------------------------------------------------------- TDV-03 IBAN


def _mod97(numeric):
    """ISO 13616 mod-97, computed digit by digit (no big ints)."""
    rem = 0
    for ch in numeric:
        rem = (rem * 10 + int(ch)) % 97
    return rem


def _iban_to_numeric(iban):
    rearranged = iban[4:] + iban[:4]
    out = []
    for ch in rearranged:
        if ch.isalpha():
            out.append(str(ord(ch) - 55))  # A=10 ... Z=35
        else:
            out.append(ch)
    return "".join(out)


def iban_check_digits(bban):
    """Compute the two IBAN check digits for a 22-digit TR BBAN."""
    numeric = _iban_to_numeric("TR00" + bban)
    return "%02d" % (98 - _mod97(numeric))


def format_iban(iban):
    """Group an IBAN in fours: TR33 0006 1005 1978 6457 8413 26."""
    s = re.sub(r"\s+", "", str(iban)).upper()
    return " ".join(s[i:i + 4] for i in range(0, len(s), 4))


def validate_iban(value):
    s = re.sub(r"\s+", "", str(value)).upper()
    if not s.startswith("TR"):
        return _result("iban", False,
                       "Turkish IBANs start with 'TR' (got %r)."
                       % str(value)[:6])
    if len(s) != 26:
        return _result("iban", False,
                       "Turkish IBANs are 26 characters (got %d)."
                       % len(s))
    if not re.fullmatch(r"TR\d{24}", s):
        return _result("iban", False,
                       "After 'TR', a Turkish IBAN must contain only "
                       "digits.")
    bank_code = s[4:9]
    reserved = s[9]
    account = s[10:]
    detail = {
        "normalized": s,
        "formatted": format_iban(s),
        "bank_code": bank_code,
        "bank": BANKS.get(bank_code),
        "reserved_digit": reserved,
        "account_part": account,
    }
    warnings = []
    if detail["bank"] is None:
        warnings.append("Bank code %s is not in the TCMB participant "
                        "table — the IBAN can still be valid." % bank_code)
    if reserved != "0":
        warnings.append("Reserved digit is %s (usually 0)." % reserved)
    if _mod97(_iban_to_numeric(s)) != 1:
        return _result("iban", False,
                       "Checksum (mod-97) failed. Check for a typo.",
                       detail, warnings)
    return _result("iban", True, None, detail,
                   warnings + ["Checksum is valid. This does not confirm "
                               "the account exists or belongs to anyone."])


def generate_iban(seed=None, bank_code="00062"):
    """A valid synthetic TR IBAN for tests and fixtures.

    Uses a real bank code (default 00062, Garanti BBVA), reserved
    digit 0, and a random 16-digit account part, with check digits
    computed by mod-97. Arithmetic only — see generate_tckn.
    """
    if bank_code not in BANKS:
        raise ValueError("unknown bank code: %s" % bank_code)
    rng = random.Random(seed)
    account = "".join(str(rng.randint(0, 9)) for _ in range(16))
    bban = bank_code + "0" + account
    return "TR" + iban_check_digits(bban) + bban


# ---------------------------------------------------------------- TDV-04 phone


def _strip_phone(value):
    s = str(value).strip()
    if s.startswith("+"):
        return "+" + re.sub(r"\D", "", s[1:])
    return re.sub(r"\D", "", s)


def validate_phone(value):
    raw = _strip_phone(value)
    s = raw
    if s.startswith("+90"):
        s = s[3:]
    elif s.startswith("0090"):
        s = s[4:]
    elif s.startswith("90") and len(s) == 12:
        s = s[2:]
    elif s.startswith("0"):
        s = s[1:]
    detail = {"input": str(value)}
    # Short service numbers: 112, 155, 156, 110.
    if re.fullmatch(r"1(12|55|56|10)", raw):
        return _result("phone", True, None,
                       {**detail, "kind_detail": "short service number",
                        "normalized": raw})
    # 444 numbers: 444 + 4 digits.
    if re.fullmatch(r"444\d{4}", s):
        return _result("phone", True, None,
                       {**detail, "kind_detail": "444 service number",
                        "normalized": "0" + s,
                        "e164": "+90" + s})
    # 0850 / 0800 numbers: 850/800 + 7 digits.
    if re.fullmatch(r"(850|800)\d{7}", s):
        return _result("phone", True, None,
                       {**detail, "kind_detail": "0850/0800 service number",
                        "normalized": "0" + s,
                        "e164": "+90" + s})
    if len(s) != 10 or not s.isdigit():
        return _result(
            "phone", False,
            "Turkish numbers are 10 digits after the country/trunk "
            "code (got %d digits)." % len(re.sub(r"\D", "", s)))
    if s.startswith("5"):
        return _result("phone", True, None,
                       {**detail, "kind_detail": "mobile",
                        "normalized": "0" + s,
                        "formatted": "(0%s) %s %s %s"
                        % (s[:3], s[3:6], s[6:8], s[8:]),
                        "e164": "+90" + s})
    area = s[:3]
    rest = s[3:]
    if area[0] in "234" and rest.isdigit():
        city = AREA_CODES.get(area)
        warnings = []
        if city is None:
            warnings.append("Area code %s is not in the verified list — "
                            "the format is valid." % area)
        return _result("phone", True, None,
                       {**detail, "kind_detail": "landline",
                        "area_code": area, "city": city,
                        "normalized": "0" + s,
                        "formatted": "(0%s) %s %s %s"
                        % (area, rest[:3], rest[3:5], rest[5:]),
                        "e164": "+90" + s},
                       warnings)
    return _result("phone", False,
                   "Not a valid Turkish number: 10-digit numbers start "
                   "with 5 (mobile) or a landline area code.")


# ---------------------------------------------------------------- TDV-05 plate


_PLATE_RE = re.compile(
    r"^([0-9]{2})\s?([A-Z]{1,3})\s?([0-9]{2,4})$")


def validate_plate(value):
    s = tr_upper(str(value).strip())
    s = re.sub(r"\s+", " ", s)
    m = _PLATE_RE.fullmatch(s)
    if not m:
        return _result(
            "plate", False,
            "Plates are <province 01-81> <1-3 letters A-Z> <2-4 digits> "
            "(e.g. '34 AB 123').")
    code, letters, digits = m.groups()
    province = PROVINCES.get(code)
    if province is None:
        return _result("plate", False,
                       "Province code %s does not exist (01-81)." % code)
    if len(letters) == 3 and len(digits) == 4:
        return _result(
            "plate", False,
            "3-letter plates have 2-3 digits, not 4 ('34 ABC 1234').")
    if any(ch in "ÇĞİÖŞÜ" for ch in str(value).upper()):
        return _result(
            "plate", False,
            "Turkish plates use A-Z only (no Ç/Ğ/İ/Ö/Ş/Ü).")
    return _result("plate", True, None,
                   {"normalized": "%s %s %s" % (code, letters, digits),
                    "province_code": code, "province": province,
                    "letters": letters, "digits": digits})


# ---------------------------------------------------------------- TDV-06 postal code


def validate_postal_code(value):
    s = _digits_only(value)
    if not s.isdigit():
        return _result("postal", False,
                       "Postal codes contain only digits (got %r)."
                       % value)
    if len(s) != 5:
        return _result("postal", False,
                       "Turkish postal codes are 5 digits (got %d)."
                       % len(s))
    code = s[:2]
    province = PROVINCES.get(code)
    if province is None:
        return _result("postal", False,
                       "First two digits %s are not a province code "
                       "(01-81)." % code)
    return _result("postal", True, None,
                   {"normalized": s, "province_code": code,
                    "province": province})


# ---------------------------------------------------------------- formatters


def format_money(amount):
    """Format a number as Turkish money: 1250.5 -> '1.250,50 ₺'."""
    try:
        value = float(amount)
    except (TypeError, ValueError):
        raise ValueError("money needs a number, got %r" % (amount,))
    sign = "-" if value < 0 else ""
    whole, frac = ("%0.2f" % abs(value)).split(".")
    groups = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    return "%s%s,%s ₺" % (sign, ".".join(reversed(groups)), frac)


def parse_money(text):
    """Parse Turkish money text ('1.250,50' or '1.250,50 ₺') to float."""
    s = str(text).strip().replace("₺", "").replace("TL", "").strip()
    s = s.replace(".", "").replace(",", ".")
    return float(s)


def format_date_tr(value):
    """Format an ISO date as a Turkish date: 2026-11-18 -> 18.11.2026."""
    if isinstance(value, date):
        d = value
    else:
        parts = str(value).split("-")
        if len(parts) != 3:
            raise ValueError("date needs YYYY-MM-DD, got %r" % (value,))
        d = date(int(parts[0]), int(parts[1]), int(parts[2]))
    return "%02d.%02d.%04d" % (d.day, d.month, d.year)


# ---------------------------------------------------------------- detect + audit

VALIDATORS = {
    "tckn": validate_tckn,
    "vkn": validate_vkn,
    "iban": validate_iban,
    "phone": validate_phone,
    "plate": validate_plate,
    "postal": validate_postal_code,
}


def detect(value):
    """Guess the type of a raw Turkish value, then validate it."""
    s = str(value).strip()
    compact = _digits_only(s)
    if re.fullmatch(r"TR[\s0-9A-Za-z]{24,30}", s, re.IGNORECASE):
        return validate_iban(s)
    if re.fullmatch(r"\d{11}", compact):
        # 11 digits starting with 0 cannot be a TCKN (first digit
        # is never 0) — it is a phone number with its trunk 0.
        if compact.startswith("0"):
            return validate_phone(compact)
        return validate_tckn(compact)
    if re.fullmatch(r"\d{10}", compact):
        # 10 digits are ambiguous: a VKN, or a mobile without its
        # trunk 0. Mobiles always start with 5, so prefer phone
        # there; otherwise prefer VKN and fall back to phone.
        if compact.startswith("5"):
            return validate_phone(compact)
        vkn = validate_vkn(compact)
        if vkn["valid"]:
            return vkn
        return validate_phone(compact)
    # Plate before postal: "34 AB 123" compacts to 5 digits ("34123"),
    # which would otherwise be misread as a postal code.
    if _PLATE_RE.fullmatch(tr_upper(s)):
        return validate_plate(s)
    if re.fullmatch(r"\d{5}", compact):
        return validate_postal_code(compact)
    phone = validate_phone(s)
    if phone["valid"]:
        return phone
    return _result("unknown", False,
                   "Could not detect the type of %r — try 'validate "
                   "<type> <value>' with an explicit type." % value)


def audit_csv(path, column, kind=None):
    """Validate one column of a CSV file, row by row.

    kind None means auto-detect per cell. Returns a summary dict.
    """
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or column not in reader.fieldnames:
            raise ValueError("column %r not in CSV header %s"
                             % (column, reader.fieldnames))
        rows = list(reader)
    findings = []
    valid_count = 0
    for i, row in enumerate(rows, start=2):  # line 1 is the header
        value = (row.get(column) or "").strip()
        if not value:
            findings.append({"row": i, "value": value, "kind": kind,
                             "valid": False,
                             "reason": "Empty cell."})
            continue
        res = (VALIDATORS[kind](value) if kind
               else detect(value))
        if res["valid"]:
            valid_count += 1
        else:
            findings.append({"row": i, "value": value,
                             "kind": res["kind"], "valid": False,
                             "reason": res["reason"]})
    return {
        "file": path, "column": column, "kind": kind or "auto",
        "rows": len(rows), "valid": valid_count,
        "invalid": len(findings), "findings": findings,
    }


# ---------------------------------------------------------------- CLI


def _print_result(res, as_json):
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    status = "VALID" if res["valid"] else "INVALID"
    print("[%s] %s: %s" % (status, res["kind"], res["reason"] or "OK"))
    for key, val in res["detail"].items():
        print("    %s: %s" % (key, val))
    for warn in res["warnings"]:
        print("    warning: %s" % warn)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="turkish_data_validation.py",
        description="Validate and format Turkish data (TCKN, VKN, "
                    "IBAN, phone, plate, postal code).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="Validate one value.")
    p_val.add_argument("type", choices=sorted(VALIDATORS))
    p_val.add_argument("value")
    p_val.add_argument("--json", action="store_true")

    p_det = sub.add_parser("detect", help="Detect the type, then validate.")
    p_det.add_argument("value")
    p_det.add_argument("--json", action="store_true")

    p_fmt = sub.add_parser("format", help="Format one value.")
    p_fmt.add_argument("type", choices=["iban", "phone", "money",
                                        "date", "upper", "lower"])
    p_fmt.add_argument("value")

    p_gen = sub.add_parser("generate",
                           help="Generate a valid synthetic test value.")
    p_gen.add_argument("type", choices=["tckn", "vkn", "iban"])
    p_gen.add_argument("--seed", type=int, default=None)
    p_gen.add_argument("--bank", default="00062",
                       help="IBAN bank code (default 00062).")

    p_aud = sub.add_parser("audit", help="Validate one CSV column.")
    p_aud.add_argument("file")
    p_aud.add_argument("--column", required=True)
    p_aud.add_argument("--type", choices=sorted(VALIDATORS), default=None)
    p_aud.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            res = VALIDATORS[args.type](args.value)
            _print_result(res, args.json)
            return 0 if res["valid"] else 1
        if args.command == "detect":
            res = detect(args.value)
            _print_result(res, args.json)
            return 0 if res["valid"] else 1
        if args.command == "format":
            if args.type == "iban":
                print(format_iban(args.value))
            elif args.type == "phone":
                res = validate_phone(args.value)
                if not res["valid"]:
                    print("INVALID: %s" % res["reason"], file=sys.stderr)
                    return 1
                print(res["detail"].get("formatted")
                      or res["detail"].get("normalized"))
            elif args.type == "money":
                print(format_money(args.value))
            elif args.type == "date":
                print(format_date_tr(args.value))
            elif args.type == "upper":
                print(tr_upper(args.value))
            elif args.type == "lower":
                print(tr_lower(args.value))
            return 0
        if args.command == "generate":
            if args.type == "tckn":
                print(generate_tckn(args.seed))
            elif args.type == "vkn":
                print(generate_vkn(args.seed))
            elif args.type == "iban":
                print(format_iban(generate_iban(args.seed, args.bank)))
            return 0
        if args.command == "audit":
            summary = audit_csv(args.file, args.column, args.type)
            if args.json:
                print(json.dumps(summary, ensure_ascii=False, indent=2))
            else:
                print("%s: %d rows, %d valid, %d invalid."
                      % (summary["file"], summary["rows"],
                         summary["valid"], summary["invalid"]))
                for f in summary["findings"]:
                    print("  row %d: %r (%s): %s"
                          % (f["row"], f["value"], f["kind"], f["reason"]))
            return 0 if summary["invalid"] == 0 else 1
    except (ValueError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())

