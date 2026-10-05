#!/bin/bash
# Website Blocker — hosts file method (Linux)
# Works in ALL browsers including Incognito
# Run with: sudo bash block.sh [block|unblock]

HOSTS="/etc/hosts"
MARKER_START="# === BLOCKED SITES ==="
MARKER_END="# === END BLOCKED SITES ==="

# ── Sites to block ──────────────────────────────
SITES=(
  "duavn.net"
  # Add more sites here, one per line
)
# ────────────────────────────────────────────────

flush_dns() {
  # Try common Linux DNS flush methods
  if systemctl is-active --quiet systemd-resolved; then
    resolvectl flush-caches
  elif command -v nscd &>/dev/null; then
    service nscd restart
  fi
}

block() {
  # Remove old block section if it exists (Linux sed: no '' after -i)
  sed -i "/$MARKER_START/,/$MARKER_END/d" "$HOSTS"

  echo "" >> "$HOSTS"
  echo "$MARKER_START" >> "$HOSTS"
  for site in "${SITES[@]}"; do
    # Skip comment lines in the array
    [[ "$site" == \#* ]] && continue
    echo "127.0.0.1   $site" >> "$HOSTS"
  done
  echo "$MARKER_END" >> "$HOSTS"

  flush_dns
  echo "✓ Blocked ${#SITES[@]} entries. Restart your browser."
}

unblock() {
  sed -i "/$MARKER_START/,/$MARKER_END/d" "$HOSTS"
  # Clean up trailing blank line left behind
  sed -i -e :a -e '/^\s*$/{$d;N;ba}' "$HOSTS"
  flush_dns
  echo "✓ All sites unblocked."
}

status() {
  if grep -q "$MARKER_START" "$HOSTS"; then
    echo "Currently blocking:"
    sed -n "/$MARKER_START/,/$MARKER_END/p" "$HOSTS" | grep "^127" | awk '{print "  →", $2}'
  else
    echo "No sites currently blocked."
  fi
}

case "$1" in
  block)   block ;;
  unblock) unblock ;;
  status)  status ;;
  *)
    echo "Usage: sudo bash block.sh [block|unblock|status]"
    echo "  block   — add all sites to hosts file"
    echo "  unblock — remove all blocks"
    echo "  status  — show what's currently blocked"
    ;;
esac
