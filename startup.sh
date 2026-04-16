#!/bin/bash
set -e

echo "=== LangBot startup ==="
echo "Running database migrations..."
alembic upgrade head

echo "Seeding lessons..."
python -m utils.seed_lessons

echo "Starting bot..."
exec python -m bot.main
