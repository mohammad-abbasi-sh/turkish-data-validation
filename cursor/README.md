# Cursor / Windsurf / Cline / Continue

The same skill, packaged for editors and agents other than Claude.

## Cursor

Copy `turkish-data-validation.mdc` into your project's
`.cursor/rules/`:

```bash
cp cursor/turkish-data-validation.mdc .cursor/rules/
```

The rule triggers on `*.{py,js,ts,tsx,md,mdx,txt,html,csv,json}`
whenever Turkish data is written or validated. The checker script
lives in `skills/turkish-data-validation/scripts/` — keep the
`skills/` directory in the repo (or copy the script next to the
rule and adjust the path in the rule).

## Windsurf

Copy `turkish-data-validation.mdc` into `.windsurf/rules/`.
Windsurf reads the same `.mdc` frontmatter (`description`,
`globs`, `alwaysApply`).

## Cline

Copy the contents of `turkish-data-validation.mdc` (minus the
frontmatter) into a `.clinerules/` file, or add the skill
directory to your workspace and point Cline at
`skills/turkish-data-validation/SKILL.md` as a rule file.

## Continue

Add the skill as a context provider: reference
`skills/turkish-data-validation/SKILL.md` in `.continue/rules/`
(or paste its contract section into a `rules` block in
`config.yaml`).

## The checker, anywhere

No install, no dependencies (Python 3.9+ stdlib only):

```bash
python3 skills/turkish-data-validation/scripts/turkish_data_validation.py validate tckn 10000000146
python3 skills/turkish-data-validation/scripts/turkish_data_validation.py audit customers.csv --column tckn
```

## MCP (any client)

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

Tools: `validate_turkish_data`, `detect_turkish_data`,
`format_turkish_data`, `generate_turkish_test_data`,
`audit_turkish_csv`, `list_turkish_checks`.
