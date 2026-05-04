.PHONY: lint format check test install install-pipx

lint:
	poetry run ruff check .

format:
	poetry run ruff format .

check:
	poetry run ruff check . && poetry run ruff format --check . && poetry run pyright

test:
	poetry run pytest -q --tb=short --no-header --cov=cctop --cov-fail-under=70

install:
	pip install .

install-pipx:
	@which pipx >/dev/null 2>&1 || { echo "pipx not found. Install with: brew install pipx"; exit 1; }
	pipx install .
