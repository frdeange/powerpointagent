#!/usr/bin/env bash
# ============================================================
# Deploy all services to Azure Container Apps
# Usage: ./scripts/deploy.sh [image-tag]
# ============================================================
set -euo pipefail

IMAGE_TAG="${1:-latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "${SCRIPT_DIR}")"

# ── Load env vars ─────────────────────────────────────────────────────────────
if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  source "${ROOT_DIR}/.env"
  set +a
fi

: "${ACR_NAME:?Set ACR_NAME in .env}"
: "${ACA_RESOURCE_GROUP:?Set ACA_RESOURCE_GROUP in .env}"
: "${ACA_LOCATION:=eastus2}"

ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"

echo "🔐 Logging into ACR: ${ACR_NAME}"
az acr login --name "${ACR_NAME}"

SERVICES=(
  "pptx-mcp-server:services/pptx-mcp-server"
  "image-mcp-server:services/image-mcp-server"
  "orchestrator:services/orchestrator"
  "bot:services/bot"
)

# ── Build & push images ────────────────────────────────────────────────────────
for entry in "${SERVICES[@]}"; do
  SERVICE_NAME="${entry%%:*}"
  SERVICE_DIR="${entry##*:}"

  echo ""
  echo "🏗️  Building ${SERVICE_NAME}:${IMAGE_TAG}"
  docker build \
    -t "${ACR_LOGIN_SERVER}/${SERVICE_NAME}:${IMAGE_TAG}" \
    -t "${ACR_LOGIN_SERVER}/${SERVICE_NAME}:latest" \
    "${ROOT_DIR}/${SERVICE_DIR}"

  echo "📤 Pushing ${SERVICE_NAME}:${IMAGE_TAG}"
  docker push "${ACR_LOGIN_SERVER}/${SERVICE_NAME}:${IMAGE_TAG}"
  docker push "${ACR_LOGIN_SERVER}/${SERVICE_NAME}:latest"
done

echo ""
echo "✅ All images built and pushed."
echo ""
echo "🚀 Deploying infrastructure with Bicep..."
az deployment group create \
  --resource-group "${ACA_RESOURCE_GROUP}" \
  --template-file "${ROOT_DIR}/infra/main.bicep" \
  --parameters "${ROOT_DIR}/infra/main.bicepparam" \
  --parameters imageTag="${IMAGE_TAG}" \
  --name "pptxagent-deploy-$(date +%Y%m%d%H%M%S)"

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📋 Getting deployment outputs..."
az deployment group show \
  --resource-group "${ACA_RESOURCE_GROUP}" \
  --name "pptxagent-deploy-$(date +%Y%m%d%H%M%S)" \
  --query properties.outputs 2>/dev/null || true
