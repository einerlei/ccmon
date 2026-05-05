.PHONY: lint format check test install release

lint:
	poetry run ruff check .

format:
	poetry run ruff format .

check:
	poetry run ruff check . && poetry run ruff format --check . && poetry run pyright

test:
	poetry run pytest -q --tb=short --no-header --cov=cctop --cov-fail-under=70

install:
	@which pipx >/dev/null 2>&1 || { echo "pipx not found. Install with: brew install pipx"; exit 1; }
	pipx install .

release:
	@test -n "$(VERSION)" || (echo "Usage: make release VERSION=x.y.z"; exit 1)
	git tag v$(VERSION)
	git push && git push --tags
