#!/usr/bin/env sh
# ---------------------------------------------------------------------------
# Запуск генератора заданий. Нужен только Python 3.10+.
#
#   ./start.sh              обычный запуск на http://127.0.0.1:8000
#   ./start.sh --auth       с аутентификацией и персональной статистикой
#   PORT=9000 ./start.sh    другой порт
#   HOST=0.0.0.0 ./start.sh доступ с других машин (сервер)
# ---------------------------------------------------------------------------
set -eu
cd "$(dirname "$0")"

command -v python3 >/dev/null 2>&1 || {
  echo "Не найден python3. Установите Python 3.10 или новее." >&2
  exit 1
}

AUTH=""
for arg in "$@"; do
  if [ "$arg" = "--auth" ]; then AUTH="--auth"; fi
done

exec python3 -m boolgen.cli serve \
  --host "${HOST:-127.0.0.1}" \
  --port "${PORT:-8000}" \
  --pool "${POOL:-boolgen_pool.sqlite}" \
  $AUTH
