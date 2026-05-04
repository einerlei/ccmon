.PHONY: lint format check test install

lint:
	poetry run ruff check .

format:
	poetry run ruff format .

check:
	poetry run ruff check . && poetry run ruff format --check . && poetry run pyright

test:
	poetry run pytest -q --tb=short --no-header --cov=dashboard --cov-fail-under=70

install:
	pipx install .
