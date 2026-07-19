#!/usr/bin/env bash
# Полный сброс канонического демо GigaScope.
# ВНИМАНИЕ: удаляет контейнер NEO4J_CONTAINER и его данные.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

OUROBOROS_API_URL="${OUROBOROS_API_URL:-http://localhost:8765}"
NEO4J_BOLT_URL="${NEO4J_BOLT_URL:-bolt://localhost:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"
NEO4J_CONTAINER="${NEO4J_CONTAINER:-gigascope-neo4j}"
NEO4J_IMAGE="${NEO4J_IMAGE:-neo4j:5}"

if [[ -z "$NEO4J_PASSWORD" ]]; then
  echo "ERROR: задайте NEO4J_PASSWORD в окружении или локальном .env" >&2
  exit 2
fi
if [[ "$NEO4J_PASSWORD" == "change-me-before-first-run" ]]; then
  echo "ERROR: замените пример NEO4J_PASSWORD перед запуском" >&2
  exit 2
fi

if docker ps >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo -n docker ps >/dev/null 2>&1; then
  DOCKER=(sudo -n docker)
else
  echo "ERROR: Docker недоступен текущему пользователю" >&2
  exit 3
fi

require_http() {
  local url="$1"
  local label="$2"
  if ! curl --fail --silent --show-error --max-time 10 "$url" >/dev/null; then
    echo "ERROR: $label недоступен: $url" >&2
    exit 4
  fi
}

wait_http() {
  local url="$1"
  local attempts="${2:-60}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if curl --fail --silent --max-time 2 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "ERROR: сервис не стал готов: $url" >&2
  return 1
}

echo "[1/5] Проверяю Ouroboros API..."
require_http "$OUROBOROS_API_URL/api/gigascope/engine/status" "Ouroboros GigaScope API"

echo "[2/5] Пересоздаю Neo4j-контейнер $NEO4J_CONTAINER..."
"${DOCKER[@]}" rm -f "$NEO4J_CONTAINER" >/dev/null 2>&1 || true
"${DOCKER[@]}" run -d \
  --name "$NEO4J_CONTAINER" \
  -p 7474:7474 \
  -p 7687:7687 \
  -e "NEO4J_AUTH=${NEO4J_USER}/${NEO4J_PASSWORD}" \
  "$NEO4J_IMAGE" >/dev/null
wait_http "http://localhost:7474/"

echo "[3/5] Инициализирую топологию..."
python3 init_topology.py \
  --bolt-url "$NEO4J_BOLT_URL" \
  --user "$NEO4J_USER" \
  --password "$NEO4J_PASSWORD"

echo "[4/5] Загружаю канонические демо-данные..."
python3 demo_seeder.py \
  --base-url "$OUROBOROS_API_URL" \
  --neo4j-url "$NEO4J_BOLT_URL" \
  --neo4j-user "$NEO4J_USER" \
  --neo4j-password "$NEO4J_PASSWORD"

echo "[5/5] Проверяю итоговое API-состояние..."
require_http "$OUROBOROS_API_URL/api/gigascope/graph" "граф GigaScope"
require_http "$OUROBOROS_API_URL/api/gigascope/engine/status" "статус движка GigaScope"

echo
echo "Готово. Каноническое демо подготовлено."
echo "Запустите SPA: python3 backend/api/gigascope_server.py"
