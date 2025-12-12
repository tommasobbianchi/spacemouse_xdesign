#!/bin/bash
# Flathub Submission Helper

set -e

APP_ID="io.github.tommaso.spacemouse_xdesign"
BRANCH="new-pr-io.github.tommaso.spacemouse_xdesign"
SRC_DIR="flathub_submission/flathub"

echo "==========================================="
echo "   SpaceMouse Bridge Flathub Submission    "
echo "==========================================="

if [ ! -d "$SRC_DIR" ]; then
    echo "Error: Submission directory not found at $SRC_DIR"
    exit 1
fi

cd "$SRC_DIR"

echo "Current status:"
git status

echo ""
echo "Attempting to create Pull Request using GitHub CLI (gh)..."
echo "If this checks for a fork and asks to create one, say 'Yes'."

if command -v gh &> /dev/null; then
    # --web opens it in browser if verified, but here we want to create it.
    # If the user is not logged in, this will fail or prompt.
    gh pr create \
        --title "Add $APP_ID" \
        --body "Initial submission of SpaceMouse Bridge (v0.2.0)." \
        --head "$BRANCH"
else
    echo "Error: 'gh' tool not found. Please install GitHub CLI or push manually."
    echo "Manual Steps:"
    echo "1. cd $SRC_DIR"
    echo "2. git push <your-fork-remote> $BRANCH"
    echo "3. Open PR on GitHub."
fi
