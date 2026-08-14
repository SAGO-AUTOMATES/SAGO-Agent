#!/usr/bin/env bash
# ==============================================================================
# SAGO Git Hooks Installer
# Installs pre-commit and pre-push hooks into the local repository
# ==============================================================================
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

if [ ! -d "$HOOKS_DIR" ]; then
    echo "❌ Error: Not a git repository or .git/hooks directory not found."
    exit 1
fi

chmod +x "$REPO_ROOT/scripts/pre-commit-check.sh"
chmod +x "$REPO_ROOT/scripts/pre-push-check.sh"

# Install pre-commit hook
cat << 'EOF' > "$HOOKS_DIR/pre-commit"
#!/usr/bin/env bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
exec "$REPO_ROOT/scripts/pre-commit-check.sh"
EOF
chmod +x "$HOOKS_DIR/pre-commit"

# Install pre-push hook
cat << 'EOF' > "$HOOKS_DIR/pre-push"
#!/usr/bin/env bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
exec "$REPO_ROOT/scripts/pre-push-check.sh"
EOF
chmod +x "$HOOKS_DIR/pre-push"

echo "✅ [SAGO] Git pre-commit and pre-push hooks successfully installed into .git/hooks/"
