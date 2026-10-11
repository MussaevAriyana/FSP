#!/bin/sh
set -e
# SEED_DEMO=1 — один раз наполнить пустую базу демо-данными (70 кандидатов, 5 работодателей)
if [ "${SEED_DEMO:-0}" = "1" ] && [ ! -s "$DB_PATH" ]; then
  echo "Наполняю демо-данными…"
  python scripts/seed.py > /dev/null 2>&1 || echo "Не удалось создать демо-данные"
fi
# SQLite + несколько потоков в одном процессе: один воркер gthread
exec gunicorn run:app --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 8 --timeout 60 --access-logfile -
