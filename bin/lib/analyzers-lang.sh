# analyzers-lang.sh -- per-language analyzer functions for run-analysis.sh.
#
# Sourced by bin/run-analysis.sh (which owns `set -euo pipefail`); do NOT declare
# set -e here -- these functions inherit it, and the &&/|| and `|| true` guards in
# their bodies are load-bearing under that option state. Functions are pure (argv
# in, stdout JSON out); they call common.sh helpers (find_tool, read_project_config)
# and read $PROJECT_ROOT at call time, both provided by the sourcing script.

# ── Per-language analysis functions ──────────────────────────────────────────

analyze_php() {
  local file="$1" findings=""
  local level=$(read_project_config "$PROJECT_ROOT" ".claude/phpstan-level" "8")
  local standard=$(read_project_config "$PROJECT_ROOT" ".claude/phpcs-standard" "PSR12")

  # PHPStan
  local phpstan=$(find_tool "$PROJECT_ROOT" "vendor/bin/phpstan" "phpstan")
  if [ -n "$phpstan" ]; then
    local output
    local exit_code
    output=$("$phpstan" analyse "$file" --level="$level" --no-progress --error-format=json 2>/dev/null) && exit_code=0 || exit_code=$?

    # Parse JSON output if available, fall back to raw
    local parsed
    parsed=$(python3 -c '
import json, sys
file, output, level = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    data = json.loads(output)
    for f_data in data.get("files", {}).values():
        for msg in f_data.get("messages", []):
            print(json.dumps({
                "file": file,
                "line": msg.get("line", 0),
                "severity": "error",
                "rule": "ENF-POST-007",
                "tool": "phpstan-level-" + level,
                "message": msg.get("message", "")
            }))
except (json.JSONDecodeError, Exception):
    pass
' "$file" "$output" "$level" 2>/dev/null)

    if [ -z "$parsed" ] && [ $exit_code -ne 0 ]; then
      # Fallback: raw output parsing
      local raw_exit
      output=$("$phpstan" analyse "$file" --level="$level" --no-progress 2>&1) && raw_exit=0 || raw_exit=$?
      if [ $raw_exit -ne 0 ] || echo "$output" | grep -q "errors"; then
        parsed=$(python3 -c '
import json, sys, re
file, output, level = sys.argv[1], sys.argv[2], sys.argv[3]
for match in re.finditer(r"Line\s+(\d+)\s*\n\s*(.*?)(?=\n\s*(?:Line|\d+ error|$))", output, re.DOTALL):
    line_num = int(match.group(1))
    msg = match.group(2).strip()
    print(json.dumps({
        "file": file,
        "line": line_num,
        "severity": "error",
        "rule": "ENF-POST-007",
        "tool": "phpstan-level-" + level,
        "message": msg
    }))
' "$file" "$output" "$level" 2>/dev/null)
      fi
    fi
    [ -n "$parsed" ] && findings="${findings}${parsed}"$'\n'
  else
    findings="${findings}$(python3 -c '
import json, sys
print(json.dumps({
    "file": sys.argv[1], "line": 0, "severity": "warning",
    "rule": "ENF-POST-007", "tool": "phpstan",
    "message": "PHPStan not found. Install: composer require --dev phpstan/phpstan"
}))' "$file" 2>/dev/null)"$'\n'
  fi

  # PHPCS
  local phpcs=$(find_tool "$PROJECT_ROOT" "vendor/bin/phpcs" "phpcs")
  if [ -n "$phpcs" ]; then
    local output
    output=$("$phpcs" "$file" --standard="$standard" --report=json 2>/dev/null) || true

    local parsed
    parsed=$(python3 -c '
import json, sys
file, output, standard = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    data = json.loads(output)
    for path, f_data in data.get("files", {}).items():
        for msg in f_data.get("messages", []):
            print(json.dumps({
                "file": file,
                "line": msg.get("line", 0),
                "severity": msg.get("type", "error").lower(),
                "rule": "ENF-POST-007",
                "tool": "phpcs-" + standard,
                "message": msg.get("message", "")
            }))
except (json.JSONDecodeError, Exception):
    pass
' "$file" "$output" "$standard" 2>/dev/null)
    [ -n "$parsed" ] && findings="${findings}${parsed}"$'\n'
  fi

  echo -n "$findings"
}

analyze_xml() {
  local file="$1"
  if command -v xmllint &>/dev/null; then
    local output exit_code
    output=$(xmllint --noout "$file" 2>&1) && exit_code=0 || exit_code=$?
    if [ $exit_code -ne 0 ]; then
      python3 -c '
import json, sys, re
file, output = sys.argv[1], sys.argv[2]
for match in re.finditer(r":(\d+):\s*(.*)", output):
    print(json.dumps({
        "file": file,
        "line": int(match.group(1)),
        "severity": "error",
        "rule": "ENF-POST-007",
        "tool": "xmllint",
        "message": match.group(2).strip()
    }))
' "$file" "$output" 2>/dev/null
    fi
  else
    python3 -c '
import json, sys
print(json.dumps({
    "file": sys.argv[1], "line": 0, "severity": "warning",
    "rule": "ENF-POST-007", "tool": "xmllint",
    "message": "xmllint not found. Install: sudo apt install libxml2-utils"
}))' "$file" 2>/dev/null
  fi
}

analyze_js_ts() {
  local file="$1"
  local eslint=$(find_tool "$PROJECT_ROOT" "node_modules/.bin/eslint" "eslint")
  if [ -n "$eslint" ]; then
    local output
    output=$("$eslint" "$file" --format=json 2>/dev/null) || true

    python3 -c '
import json, sys
file, output = sys.argv[1], sys.argv[2]
try:
    data = json.loads(output)
    for result in data:
        for msg in result.get("messages", []):
            sev = "error" if msg.get("severity", 0) == 2 else "warning"
            rule_id = msg.get("ruleId", "unknown")
            print(json.dumps({
                "file": file,
                "line": msg.get("line", 0),
                "severity": sev,
                "rule": "ENF-POST-007",
                "tool": "eslint/" + str(rule_id),
                "message": msg.get("message", "")
            }))
except (json.JSONDecodeError, Exception):
    pass
' "$file" "$output" 2>/dev/null
  else
    python3 -c '
import json, sys
print(json.dumps({
    "file": sys.argv[1], "line": 0, "severity": "warning",
    "rule": "ENF-POST-007", "tool": "eslint",
    "message": "ESLint not found. Install: npm install --save-dev eslint"
}))' "$file" 2>/dev/null
  fi
}

analyze_python() {
  local file="$1"
  if command -v ruff &>/dev/null; then
    local output
    output=$(ruff check "$file" --output-format=json 2>/dev/null) || true

    python3 -c '
import json, sys
file, output = sys.argv[1], sys.argv[2]
try:
    data = json.loads(output)
    for item in data:
        print(json.dumps({
            "file": file,
            "line": item.get("location", {}).get("row", 0),
            "severity": "error",
            "rule": "ENF-POST-007",
            "tool": "ruff/" + item.get("code", "unknown"),
            "message": item.get("message", "")
        }))
except (json.JSONDecodeError, Exception):
    pass
' "$file" "$output" 2>/dev/null
  elif command -v flake8 &>/dev/null; then
    local output
    output=$(flake8 "$file" --format='%(path)s:%(row)d:%(col)d: %(code)s %(text)s' 2>&1) || true
    python3 -c '
import json, sys, re
file, output = sys.argv[1], sys.argv[2]
for match in re.finditer(r":(\d+):\d+:\s+(\S+)\s+(.*)", output):
    print(json.dumps({
        "file": file,
        "line": int(match.group(1)),
        "severity": "error",
        "rule": "ENF-POST-007",
        "tool": "flake8/" + match.group(2),
        "message": match.group(3).strip()
    }))
' "$file" "$output" 2>/dev/null
  else
    python3 -c '
import json, sys
print(json.dumps({
    "file": sys.argv[1], "line": 0, "severity": "warning",
    "rule": "ENF-POST-007", "tool": "python-lint",
    "message": "No Python linter found. Install: pip install ruff"
}))' "$file" 2>/dev/null
  fi
}

analyze_rust() {
  local file="$1"
  if command -v cargo &>/dev/null && [ -n "$PROJECT_ROOT" ]; then
    local output
    output=$(cd "$PROJECT_ROOT" && cargo check --message-format=json 2>/dev/null) || true

    python3 -c '
import json, sys
file, output = sys.argv[1], sys.argv[2]
for line in output.strip().split("\n"):
    if not line.strip():
        continue
    try:
        data = json.loads(line)
        if data.get("reason") == "compiler-message":
            msg = data.get("message", {})
            spans = msg.get("spans", [])
            line_num = spans[0].get("line_start", 0) if spans else 0
            fname = spans[0].get("file_name", file) if spans else file
            print(json.dumps({
                "file": fname,
                "line": line_num,
                "severity": msg.get("level", "error"),
                "rule": "ENF-POST-007",
                "tool": "cargo-check",
                "message": msg.get("message", "")
            }))
    except (json.JSONDecodeError, Exception):
        pass
' "$file" "$output" 2>/dev/null
  fi
}

analyze_go() {
  local file="$1"
  if command -v go &>/dev/null; then
    local output
    output=$(go vet "$file" 2>&1) || true
    if [ -n "$output" ]; then
      python3 -c '
import json, sys, re
file, output = sys.argv[1], sys.argv[2]
for match in re.finditer(r":(\d+)(?::\d+)?:\s*(.*)", output):
    print(json.dumps({
        "file": file,
        "line": int(match.group(1)),
        "severity": "error",
        "rule": "ENF-POST-007",
        "tool": "go-vet",
        "message": match.group(2).strip()
    }))
' "$file" "$output" 2>/dev/null
    fi
  fi
}

analyze_graphql() {
  local file="$1"
  if [ -z "$PROJECT_ROOT" ]; then return; fi

  python3 -c '
import json, re, os, glob as g, sys

file = sys.argv[1]
project_root = sys.argv[2]
with open(file) as f:
    content = f.read()

findings = []
for match in re.finditer("(?:class|cacheIdentity):\\s*\"([^\"]+)\"", content):
    classname = match.group(1)
    classpath = classname.replace("\\", "/").replace("\\", "/")
    basename = os.path.basename(classpath) + ".php"
    dirpart = os.path.dirname(classpath)

    found = False
    for root, dirs, files in os.walk(project_root):
        if basename in files and (not dirpart or dirpart in root.replace(os.sep, "/")):
            found = True
            break

    if not found:
        findings.append({
            "file": file,
            "line": content[:match.start()].count("\n") + 1,
            "severity": "error",
            "rule": "ENF-POST-007",
            "tool": "graphql-class-ref",
            "message": f"Class \"{classname}\" not found on disk (expected: {classpath}.php)"
        })

for f in findings:
    print(json.dumps(f))
' "$file" "$PROJECT_ROOT" 2>/dev/null
}
