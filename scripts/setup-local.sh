#!/usr/bin/env bash
# ============================================================
# Local development setup
# Sets up virtual environments for all services
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "${SCRIPT_DIR}")"

SERVICES=(
  "services/pptx-mcp-server"
  "services/image-mcp-server"
  "services/orchestrator"
  "services/bot"
)

echo "🐍 Setting up Python virtual environments..."

for SERVICE_DIR in "${SERVICES[@]}"; do
  SERVICE_NAME="$(basename "${SERVICE_DIR}")"
  FULL_DIR="${ROOT_DIR}/${SERVICE_DIR}"

  if [[ ! -f "${FULL_DIR}/requirements.txt" ]]; then
    echo "⚠️  Skipping ${SERVICE_NAME} — no requirements.txt found"
    continue
  fi

  echo ""
  echo "📦 Installing ${SERVICE_NAME}..."
  pushd "${FULL_DIR}" > /dev/null

  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip -q
  .venv/bin/pip install -r requirements.txt -q

  # Install pytest for testing
  .venv/bin/pip install pytest pytest-asyncio -q

  popd > /dev/null
  echo "✅ ${SERVICE_NAME} ready"
done

echo ""
echo "🎉 All services set up."
echo ""
echo "To activate a service environment:"
echo "  source services/pptx-mcp-server/.venv/bin/activate"
echo ""
echo "To run tests:"
echo "  cd services/pptx-mcp-server && ../.venv/bin/pytest tests/ -v"
echo ""
echo "Don't forget to copy .env.example → .env and fill in your values!"
