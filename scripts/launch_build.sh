#!/usr/bin/env bash
# Dispatch a build ONLY if preflight passes. Use this instead of `gh workflow run`.
#
# Exists because the checklist kept being skipped. Three builds have now died on
# things preflight either did catch or would have caught if it had been run, so
# the check is no longer optional -- it is the only door to the workflow.
#
# Usage: scripts/launch_build.sh <repo-url> <branch> <name> [extra -f args...]
set -euo pipefail
REPO_URL="${1:?repo url}"; BRANCH="${2:?branch}"; NAME="${3:?short name}"; shift 3
SLUG="$(echo "$REPO_URL" | sed -E 's#https://github.com/##; s#\.git$##')"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== preflight $SLUG@$BRANCH"
if ! python3 "$HERE/preflight.py" "$SLUG" "$BRANCH" --dry-run; then
  echo
  echo "REFUSING to launch '$NAME' -- preflight reported a BLOCKER."
  echo "Override deliberately with FORCE=1 if you know why it is wrong."
  [ "${FORCE:-0}" = "1" ] || exit 1
  echo "FORCE=1 set; launching anyway."
fi
echo
gh workflow run build-raphael.yml \
  -f kernel_repo="$REPO_URL" -f kernel_branch="$BRANCH" \
  -f localversion="-$NAME" "$@"
echo "launched $NAME"
