#!/usr/bin/env bash
set -euo pipefail

# Playwright e2e test runner wrapper
# - Injects LD_LIBRARY_PATH for environments where Playwright's Chromium
#   system deps (libnspr4, libnss3, etc.) aren't installed globally.
# - CI environments (Ubuntu + Playwright system deps) pass through cleanly.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/.."

# Local fallback libs for environments without system-level nspr/nss
PLAYWRIGHT_LIBS="$HOME/.local/playwright-libs/extracted/usr/lib/x86_64-linux-gnu"
if [ -d "$PLAYWRIGHT_LIBS" ]; then
  export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+${LD_LIBRARY_PATH}:}${PLAYWRIGHT_LIBS}"
fi

cd "$PROJECT_ROOT/apps/web"
exec npx playwright "$@"
