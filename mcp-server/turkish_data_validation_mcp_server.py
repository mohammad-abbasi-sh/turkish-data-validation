#!/usr/bin/env python3
"""MCP server for turkish-data-validation — expose the Turkish data
validator as tools for any MCP client.

Zero-dependency (Python standard library only). Speaks JSON-RPC 2.0
over stdio, newline-delimited, following the MCP lifecycle:

    initialize -> notifications/initialized -> tools/list -> tools/call

Tools:
    validate_turkish_data
        type   tckn | vkn | iban | phone | plate | postal (required)
        value  the value to validate (required)
    detect_turkish_data
        value  a raw Turkish value; the type is guessed, then validated
    format_turkish_data
        kind   iban | phone | money | date | upper | lower (required)
        value  the value to format (required)
    generate_turkish_test_data
        type   tckn | vkn | iban (required)
        seed   optional integer seed (deterministic output)
        bank   IBAN bank code, 5-digit IBAN form (default 00062)
    audit_turkish_csv
        file    CSV file path (required)
        column  column name to validate (required)
        type    tckn | vkn | iban | phone | plate | postal, or omit
                to auto-detect per cell
    list_turkish_checks
        (no arguments) the check table: what each TDV code validates

validate/detect/audit run skills/turkish-data-validation/scripts/
turkish_data_validation.py as a subprocess with --json and return
the findings. Exit-code semantics are preserved in the returned
text (0 = valid, 1 = invalid / findings, 2 = usage error).
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent / "skills" / "turkish-data-validation" / "scripts" \
    / "turkish_data_validation.py"

SERVER_INFO = {"name": "turkish-data-validation", "version": "0.1.0"}
PROTOCOL_VERSION = "2024-11-05"

CHECKS = """Turkish data checks (TDV-01..TDV-06):
TDV-01 tckn   — T.C. Kimlik No: 11 digits, first digit not 0, d10 =
  ((d1+d3+d5+d7+d9)*7 - (d2+d4+d6+d8)) mod 10, d11 = sum(first 10) mod 10.
TDV-02 vkn    — Vergi Kimlik No: 10 digits, one checksum (see
  references/validation-rules.md). An 11-digit input is validated
  as a TCKN, which individuals use as their tax ID.
TDV-03 iban   — Turkish IBAN: TR + 24 digits, ISO 13616 mod-97;
  decodes bank code (5 digits), reserved digit, account part, and
  names the bank from the TCMB participant table when known.
TDV-04 phone  — mobile (5xx, 10 digits), landline (0 + 3-digit area
  + 7 digits), 444 xxxx, 0850/0800, short numbers (112/155/156/110).
  Normalizes to E.164 (+90...) and formats as (0532) 123 45 67.
TDV-05 plate  — licence plate: province code 01-81 + 1-3 letters
  (A-Z) + 2-4 digits; resolves the province name.
TDV-06 postal — postal code: 5 digits, first two are the province
  code 01-81; resolves the province name.
Formatters: money (1.250,50 TL), dates (18.11.2026), Turkish case
(istanbul -> ISTANBUL, not ISTANBUL).
A passing checksum only proves the digits are mutually consistent —
never proof the number was issued or belongs to anyone."""


def _run_cli(args, timeout=120):
    proc = subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True, text=True, timeout=timeout)
    return proc


def run_validate(args):
    kind = args.get("type")
    value = args.get("value")
    if kind not in ("tckn", "vkn", "iban", "phone", "plate", "postal"):
        raise ValueError("validate_turkish_data requires 'type' "
                         "(tckn|vkn|iban|phone|plate|postal) and 'value'")
    if value is None:
        raise ValueError("validate_turkish_data requires 'value'")
    proc = _run_cli(["validate", kind, str(value), "--json"])
    try:
        res = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        res = {}
    lines = ["validate exit code: %d" % proc.returncode]
    if res:
        lines.append("VALID" if res.get("valid") else "INVALID")
        if res.get("reason"):
            lines.append(res["reason"])
        for key, val in res.get("detail", {}).items():
            lines.append("%s: %s" % (key, val))
        for warn in res.get("warnings", []):
            lines.append("warning: %s" % warn)
    if proc.stderr.strip():
        lines.append("stderr: %s" % proc.stderr.strip())
    return "\n".join(lines)


def run_detect(args):
    value = args.get("value")
    if value is None:
        raise ValueError("detect_turkish_data requires 'value'")
    proc = _run_cli(["detect", str(value), "--json"])
    try:
        res = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        res = {}
    lines = ["detect exit code: %d" % proc.returncode]
    if res:
        lines.append("type: %s — %s"
                     % (res.get("kind"),
                        "VALID" if res.get("valid") else "INVALID"))
        if res.get("reason"):
            lines.append(res["reason"])
        for key, val in res.get("detail", {}).items():
            lines.append("%s: %s" % (key, val))
    if proc.stderr.strip():
        lines.append("stderr: %s" % proc.stderr.strip())
    return "\n".join(lines)


def run_format(args):
    kind = args.get("kind")
    value = args.get("value")
    if kind not in ("iban", "phone", "money", "date", "upper", "lower"):
        raise ValueError("format_turkish_data requires 'kind' "
                         "(iban|phone|money|date|upper|lower) and 'value'")
    if value is None:
        raise ValueError("format_turkish_data requires 'value'")
    proc = _run_cli(["format", kind, str(value)])
    if proc.returncode != 0:
        return "format failed: %s" % (proc.stderr.strip()
                                      or proc.stdout.strip())
    return proc.stdout.strip()


def run_generate(args):
    kind = args.get("type")
    if kind not in ("tckn", "vkn", "iban"):
        raise ValueError("generate_turkish_test_data requires 'type' "
                         "(tckn|vkn|iban)")
    cmd = ["generate", kind]
    if args.get("seed") is not None:
        cmd += ["--seed", str(args["seed"])]
    if args.get("bank"):
        cmd += ["--bank", str(args["bank"])]
    proc = _run_cli(cmd)
    if proc.returncode != 0:
        return "generate failed: %s" % (proc.stderr.strip()
                                        or proc.stdout.strip())
    return (proc.stdout.strip()
            + "\nSynthetic test value only — arithmetic, not drawn from "
              "any register; it does not correspond to a real holder.")


def run_audit(args):
    path = args.get("file")
    column = args.get("column")
    if not path or not column:
        raise ValueError("audit_turkish_csv requires 'file' and 'column'")
    cmd = ["audit", str(path), "--column", str(column), "--json"]
    if args.get("type"):
        cmd += ["--type", str(args["type"])]
    proc = _run_cli(cmd)
    try:
        summary = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        summary = {}
    if not summary:
        return "audit failed: %s" % (proc.stderr.strip()
                                     or proc.stdout.strip())
    lines = ["%s: %d rows, %d valid, %d invalid."
             % (summary.get("file"), summary.get("rows"),
                summary.get("valid"), summary.get("invalid"))]
    for f in summary.get("findings", []):
        lines.append("  row %d: %r (%s): %s"
                     % (f["row"], f["value"], f["kind"], f["reason"]))
    return "\n".join(lines)


def run_list_checks(_args):
    return CHECKS


TOOLS = [
    {
        "name": "validate_turkish_data",
        "description": (
            "Validate one Turkish identifier with the exact rule that "
            "failed named: TCKN (11-digit national ID, two checksums), "
            "VKN (10-digit tax ID, one checksum; 11 digits are checked "
            "as TCKN), TR IBAN (mod-97, bank decoded), phone (mobile, "
            "landline, 444/0850/0800), licence plate (province 01-81), "
            "or postal code (5 digits, province in the first two). "
            "A passing checksum only proves the digits are consistent, "
            "never that the number was issued or belongs to anyone."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string",
                         "enum": ["tckn", "vkn", "iban", "phone",
                                  "plate", "postal"]},
                "value": {"type": "string",
                          "description": "The value to validate."},
            },
            "required": ["type", "value"],
        },
    },
    {
        "name": "detect_turkish_data",
        "description": (
            "Detect the type of a raw Turkish value (TCKN, VKN, IBAN, "
            "phone, plate, postal code) and validate it. Use when the "
            "type is not known in advance, e.g. a cell from a spreadsheet."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "value": {"type": "string",
                          "description": "The raw value."},
            },
            "required": ["value"],
        },
    },
    {
        "name": "format_turkish_data",
        "description": (
            "Format Turkish data the way Turkish users expect: IBAN in "
            "groups of four, phone as (0532) 123 45 67, money as "
            "1.250,50 TL, dates as 18.11.2026, and Turkish case "
            "conversion (istanbul -> ISTANBUL, not ISTANBUL)."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string",
                         "enum": ["iban", "phone", "money", "date",
                                  "upper", "lower"]},
                "value": {"type": "string",
                          "description": "The value to format."},
            },
            "required": ["kind", "value"],
        },
    },
    {
        "name": "generate_turkish_test_data",
        "description": (
            "Generate a valid synthetic Turkish test value (TCKN, VKN "
            "or IBAN) for fixtures and tests. The digits satisfy the "
            "real checksum but are arithmetic only — they do not "
            "correspond to a real person, company or account."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string",
                         "enum": ["tckn", "vkn", "iban"]},
                "seed": {"type": "integer",
                         "description": "Optional seed for deterministic "
                                        "output."},
                "bank": {"type": "string",
                         "description": "IBAN bank code, 5-digit IBAN "
                                        "form (default 00062, Garanti "
                                        "BBVA)."},
            },
            "required": ["type"],
        },
    },
    {
        "name": "audit_turkish_csv",
        "description": (
            "Validate one column of a CSV file row by row (Turkish IDs, "
            "IBANs, phones, plates or postal codes) and report the "
            "invalid rows with the exact rule each one failed. Omit "
            "'type' to auto-detect the type of each cell."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string",
                         "description": "CSV file path."},
                "column": {"type": "string",
                           "description": "Column name to validate."},
                "type": {"type": "string",
                         "enum": ["tckn", "vkn", "iban", "phone",
                                  "plate", "postal"]},
            },
            "required": ["file", "column"],
        },
    },
    {
        "name": "list_turkish_checks",
        "description": (
            "List what this skill checks: the six TDV check codes, the "
            "rule behind each one, and the formatters. Call first when "
            "unsure which check applies."),
        "inputSchema": {"type": "object", "properties": {}},
    },
]

_DISPATCH = {
    "validate_turkish_data": run_validate,
    "detect_turkish_data": run_detect,
    "format_turkish_data": run_format,
    "generate_turkish_test_data": run_generate,
    "audit_turkish_csv": run_audit,
    "list_turkish_checks": run_list_checks,
}


def _send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _handle(msg):
    method = msg.get("method", "")
    msg_id = msg.get("id")
    if method == "initialize":
        _send({"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }})
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        _send({"jsonrpc": "2.0", "id": msg_id,
               "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {}) or {}
        try:
            fn = _DISPATCH[name]
        except KeyError:
            _send({"jsonrpc": "2.0", "id": msg_id, "error": {
                "code": -32602, "message": "unknown tool: %s" % name}})
            return
        try:
            text = fn(args)
        except (ValueError, subprocess.SubprocessError) as exc:
            _send({"jsonrpc": "2.0", "id": msg_id, "error": {
                "code": -32602, "message": str(exc)}})
            return
        _send({"jsonrpc": "2.0", "id": msg_id, "result": {
            "content": [{"type": "text", "text": text}]}})
    else:
        _send({"jsonrpc": "2.0", "id": msg_id, "error": {
            "code": -32601, "message": "method not found: %s" % method}})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        _handle(msg)


if __name__ == "__main__":
    main()
