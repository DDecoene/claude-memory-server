#!/usr/bin/env bash
# Installs the Claude Code client configuration on this machine.
# Run once on each device where you use Claude Code.
#
# Prerequisites:
#   - MEMORY_API_KEY set in your shell profile (~/.zshrc or ~/.bashrc)
#   - The Tailscale Funnel URL for your Pi
#
# Usage:
#   FUNNEL_URL=https://your-pi.tail1234.ts.net ./setup.sh
set -euo pipefail

FUNNEL_URL="${FUNNEL_URL:-}"
CLAUDE_DIR="$HOME/.claude"
HOOKS_DIR="$CLAUDE_DIR/hooks"
SETTINGS="$CLAUDE_DIR/settings.json"
CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"

if [ -z "$FUNNEL_URL" ]; then
    echo "Error: set FUNNEL_URL first, e.g.:"
    echo "  FUNNEL_URL=https://your-pi.tail1234.ts.net ./setup.sh"
    exit 1
fi

mkdir -p "$HOOKS_DIR"

# ── 1. CLAUDE.md (global profile injected into every session) ─────────────────
if [ -f "$CLAUDE_MD" ]; then
    echo "⚠  $CLAUDE_MD already exists — skipping (edit it manually)"
else
    cp "$(dirname "$0")/CLAUDE.md" "$CLAUDE_MD"
    echo "✓ Created $CLAUDE_MD — edit it to fill in your personal details"
fi

# ── 2. Merge MCP server config into ~/.claude/settings.json ──────────────────
MCP_BLOCK=$(cat <<EOF
{
  "memory": {
    "type": "sse",
    "url": "$FUNNEL_URL/mcp/sse",
    "headers": {
      "X-API-Key": "\${MEMORY_API_KEY}"
    }
  }
}
EOF
)

if [ ! -f "$SETTINGS" ]; then
    # No settings file yet — create a minimal one
    cat > "$SETTINGS" <<EOF
{
  "mcpServers": $MCP_BLOCK
}
EOF
    echo "✓ Created $SETTINGS"
else
    # settings.json exists — check if memory server is already there
    if grep -q '"memory"' "$SETTINGS"; then
        echo "⚠  memory MCP server already in $SETTINGS — skipping (update manually)"
    else
        echo ""
        echo "── Add this block to the \"mcpServers\" section of $SETTINGS ──"
        echo ""
        echo "\"memory\": {"
        echo "  \"type\": \"sse\","
        echo "  \"url\": \"$FUNNEL_URL/mcp/sse\","
        echo "  \"headers\": { \"X-API-Key\": \"\${MEMORY_API_KEY}\" }"
        echo "}"
        echo ""
        echo "(Automatic merge skipped — settings.json already exists with other content)"
    fi
fi

# ── 3. MEMORY_API_KEY reminder ────────────────────────────────────────────────
echo ""
if [ -z "${MEMORY_API_KEY:-}" ]; then
    echo "⚠  MEMORY_API_KEY is not set in this shell."
    echo "   Add this to ~/.zshrc (or ~/.bashrc):"
    echo "   export MEMORY_API_KEY=your-secret-from-the-pi-dot-env"
else
    echo "✓ MEMORY_API_KEY is set"
fi

echo ""
echo "Done. Restart Claude Code and ask it to call get_profile() to verify."
