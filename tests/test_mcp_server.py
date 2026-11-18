"""End-to-end tests for the turkish-data-validation MCP server (stdio)."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
SERVER = (HERE.parent / "mcp-server"
          / "turkish_data_validation_mcp_server.py")
FIXTURE_CSV = HERE / "fixtures" / "mixed-tr.csv"


def _session(calls):
    """Run the server, send a list of request dicts, return responses."""
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, encoding="utf-8")
    try:
        payload = "".join(json.dumps(c, ensure_ascii=False) + "\n"
                          for c in calls)
        out, _ = proc.communicate(payload, timeout=120)
    finally:
        if proc.poll() is None:
            proc.kill()
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def _init():
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05",
                       "capabilities": {}, "clientInfo": {"name": "test",
                                                          "version": "0"}}}


def _call(call_id, name, args):
    return {"jsonrpc": "2.0", "id": call_id, "method": "tools/call",
            "params": {"name": name, "arguments": args}}


def _text(resps, idx=1):
    return resps[idx]["result"]["content"][0]["text"]


def test_initialize_and_list():
    resps = _session([
        _init(),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ])
    by_id = {r["id"]: r for r in resps if "id" in r}
    assert by_id[1]["result"]["serverInfo"]["name"] == \
        "turkish-data-validation"
    names = [t["name"] for t in by_id[2]["result"]["tools"]]
    assert names == ["validate_turkish_data", "detect_turkish_data",
                     "format_turkish_data", "generate_turkish_test_data",
                     "audit_turkish_csv", "list_turkish_checks"]


def test_validate_tckn_valid():
    resps = _session([
        _init(),
        _call(2, "validate_turkish_data",
              {"type": "tckn", "value": "10000000146"}),
    ])
    text = _text(resps)
    assert "exit code: 0" in text
    assert "VALID" in text


def test_validate_tckn_invalid_names_rule():
    resps = _session([
        _init(),
        _call(2, "validate_turkish_data",
              {"type": "tckn", "value": "10000000145"}),
    ])
    text = _text(resps)
    assert "exit code: 1" in text
    assert "11th digit" in text


def test_validate_iban_names_bank():
    resps = _session([
        _init(),
        _call(2, "validate_turkish_data",
              {"type": "iban",
               "value": "TR330006100519786457841326"}),
    ])
    text = _text(resps)
    assert "exit code: 0" in text
    assert "bank_code: 00061" in text


def test_detect_phone():
    resps = _session([
        _init(),
        _call(2, "detect_turkish_data",
              {"value": "0532 123 45 67"}),
    ])
    text = _text(resps)
    assert "type: phone" in text
    assert "VALID" in text


def test_format_money_and_case():
    resps = _session([
        _init(),
        _call(2, "format_turkish_data",
              {"kind": "money", "value": "1250.5"}),
        _call(3, "format_turkish_data",
              {"kind": "upper", "value": "istanbul"}),
    ])
    assert "1.250,50" in _text(resps, 1)
    assert "İSTANBUL" in _text(resps, 2)


def test_generate_tckn():
    resps = _session([
        _init(),
        _call(2, "generate_turkish_test_data",
              {"type": "tckn", "seed": 42}),
    ])
    text = _text(resps)
    assert "20433218148" in text
    assert "Synthetic test value only" in text


def test_audit_csv():
    resps = _session([
        _init(),
        _call(2, "audit_turkish_csv",
              {"file": str(FIXTURE_CSV), "column": "tckn"}),
    ])
    text = _text(resps)
    assert "5 rows, 3 valid, 2 invalid" in text
    assert "row 4" in text


def test_list_checks():
    resps = _session([
        _init(),
        _call(2, "list_turkish_checks", {}),
    ])
    text = _text(resps)
    assert "TDV-01" in text and "TDV-06" in text
    assert "mod-97" in text


def test_unknown_tool_errors():
    resps = _session([_init(), _call(2, "nope", {})])
    assert resps[1]["error"]["code"] == -32602


def test_missing_args_errors():
    resps = _session([_init(), _call(2, "validate_turkish_data", {})])
    assert resps[1]["error"]["code"] == -32602
