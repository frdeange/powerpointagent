#!/usr/bin/env bash
# post-create.sh — runs once after the devcontainer is created.
# Installs Azure CLI extensions, system tools, and Python dependencies.
set -euo pipefail

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  PowerPoint Agent — DevContainer post-create setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── System tools ──────────────────────────────────────────────────────────────
echo ""
echo "▶ Installing system tools (jq, make)..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends jq make

# ── Azure CLI extensions ───────────────────────────────────────────────────────
# NOTE: az bicep is installed via the azure-cli devcontainer feature (installBicep: true).
#       We only need to add the containerapp extension here.
echo ""
echo "▶ Installing Azure CLI extensions..."
az extension add --name containerapp --upgrade --yes 2>/dev/null || \
    az extension update --name containerapp --yes

echo "  ✓ containerapp extension ready"
echo "  ✓ bicep: $(az bicep version 2>/dev/null | head -1 || echo 'will install on first use')"

# ── Python dependencies ────────────────────────────────────────────────────────
echo ""
echo "▶ Upgrading pip and installing Python dependencies..."
pip install --upgrade pip --quiet

# Root dev tools (pytest, linting, formatting)
pip install --quiet -r requirements-dev.txt

# Service-specific dependencies
for req in \
    services/pptx-mcp-server/requirements.txt \
    services/image-mcp-server/requirements.txt \
    services/orchestrator/requirements.txt \
    services/bot/requirements.txt; do
    if [ -f "$req" ]; then
        echo "  Installing $req..."
        pip install --quiet -r "$req"
    fi
done

# ── Git configuration ─────────────────────────────────────────────────────────
echo ""
echo "▶ Configuring git..."
git config --global --add safe.directory /workspaces/powerpointAgent
git config --global core.autocrlf input
git config --global pull.rebase false

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ DevContainer ready!"
echo "  Services run directly as Python processes — no Docker needed locally."
echo "  Docker images are built remotely via: az acr build"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
