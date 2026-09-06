#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-/opt/business-english-coach}"
if [[ ! -f "${PROJECT_DIR}/docker-compose.yml" || ! -f "${PROJECT_DIR}/.env" ]]; then
  echo "Expected docker-compose.yml and .env in ${PROJECT_DIR}" >&2
  exit 1
fi

cd "${PROJECT_DIR}"
docker compose config --quiet
docker compose build --pull
docker compose run --no-deps --rm api alembic upgrade head
docker compose up -d --remove-orphans
docker compose ps
