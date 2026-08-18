#!/usr/bin/env bash
# PreToolUse hook: refuse to dispatch a kernel build that has not been preflighted.
#
# Rationale: the checklist kept being skipped by the one person it exists for.
# Builds are ~20 minutes each; several have died on things preflight catches in
# seconds. Route every dispatch through scripts/launch_build.sh, which runs
# preflight --dry-run first and refuses on a BLOCKER.
#
# Deliberate override: prefix the command with FORCE=1.
set -uo pipefail
CMD="$(cat | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null)"

case "$CMD" in
  *"gh workflow run"*build-raphael*)
    case "$CMD" in
      *launch_build.sh*|*FORCE=1*) exit 0 ;;
    esac
    cat >&2 <<'MSG'
BLOCKED: dispatch kernel builds through scripts/launch_build.sh, not `gh workflow run`.

  scripts/launch_build.sh <repo-url> <branch> <name> [-f key=value ...]

It runs `preflight.py --dry-run` first -- which exercises every patch script
against the target tree -- and refuses on a BLOCKER. Several 20-minute builds
have been lost to problems that check finds in seconds.

Override deliberately with: FORCE=1 gh workflow run ...
MSG
    exit 2 ;;
esac
exit 0
