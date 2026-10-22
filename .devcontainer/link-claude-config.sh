#!/usr/bin/env bash
# Make the host user's personal Claude Code settings available in the container.
# The host ~/.claude is mounted read-only at ~/.claude-host; login and history live in the
# named volume at $CLAUDE_CONFIG_DIR, so they survive rebuilds and stay separate from the host.
set -euo pipefail

host_dir="$HOME/.claude-host"
config_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

sudo chown "$(id -u):$(id -g)" "$config_dir"

for item in settings.json CLAUDE.md skills agents commands; do
  if [ -e "$host_dir/$item" ]; then
    ln -sfn "$host_dir/$item" "$config_dir/$item"
  fi
done
