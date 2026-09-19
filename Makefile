.PHONY: setup build up down logs seed-admin package test

setup:
	@test -f .env || cp .env.example .env
	@echo "Simdi .env icindeki JWT_SECRET_KEY ve WATCHLIST_ENCRYPTION_KEY degerlerini uretin:"
	@echo "  python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""

build:
	docker compose build

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

seed-admin:
	docker compose exec api python -m scripts.seed_admin admin $(PASSWORD)

package:
	./scripts/package_offline.sh

test:
	pytest -q
