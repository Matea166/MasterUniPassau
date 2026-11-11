#!/usr/bin/env bash
# One-button reproduction for macOS/Linux. Windows: use reproduce_all.bat.
#
#   ./reproduce_all.sh              full Table 6.2 grid (all thesis tables)
#   QUICK=1 ./reproduce_all.sh      headline configuration only (smoke test)
#   FRESH=0 ./reproduce_all.sh      keep the existing PostgreSQL volume
#
# The experiment sequence itself runs inside the container
# (scripts/run_all.sh); this wrapper only drives Docker, so the pipeline is
# identical on every platform.

set -euo pipefail
cd "$(dirname "$0")"

QUICK="${QUICK:-0}"
FRESH="${FRESH:-1}"

if ! docker info > /dev/null 2>&1; then
    echo "Docker is not running - start Docker Desktop first."
    exit 1
fi

if [ "$FRESH" = "1" ]; then
    echo "=== Removing previous containers and database volume ==="
    docker compose down -v --remove-orphans
fi

echo "=== Building self-contained images and starting services ==="
docker compose up -d --build

docker compose exec -T -e QUICK="$QUICK" app bash scripts/run_all.sh

echo ""
echo "Done. All outputs are in ./results/."
echo "Open ./results/index.html for the experiment report."
