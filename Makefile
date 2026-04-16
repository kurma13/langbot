.PHONY: up down build logs migrate seed bot api shell

# Запуск всего проекта
up:
	docker-compose up -d

# Остановка
down:
	docker-compose down

# Пересборка
build:
	docker-compose build --no-cache

# Логи
logs:
	docker-compose logs -f

logs-bot:
	docker-compose logs -f bot

# Миграции
migrate:
	docker-compose run --rm migrate

# Генерация миграции
makemigration:
	docker-compose run --rm bot alembic revision --autogenerate -m "$(name)"

# Загрузка тестовых данных
seed:
	docker-compose run --rm bot python -m utils.seed_lessons

# Запуск только бота (для разработки)
bot:
	docker-compose up -d postgres redis
	sleep 3
	python -m bot.main

# Запуск только API
api:
	docker-compose up -d postgres
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Shell в контейнере
shell:
	docker-compose exec bot bash

# Полный старт с нуля
fresh:
	docker-compose down -v
	docker-compose up -d postgres redis
	sleep 5
	docker-compose run --rm migrate
	docker-compose run --rm bot python -m utils.seed_lessons
	docker-compose up -d bot api
