.PHONY: lint format check test install release

lint:
	uv run ruff check .

format:
	uv run ruff format .

check:
	uv run ruff check . && uv run ruff format --check . && uv run pyright

test:
	uv run pytest -q --tb=short --no-header --cov=ccmon --cov-fail-under=70

install:
	@which pipx >/dev/null 2>&1 || { echo "pipx not found. Install with: brew install pipx"; exit 1; }
	pipx install . --force
	pipx ensurepath
	@if ! echo "$$PATH" | grep -q "$$HOME/.local/bin"; then \
		echo ""; \
		echo "  ccmon is installed but not yet in your PATH."; \
		echo "  Run: source ~/.zshrc"; \
	fi

release:
	@test -n "$(VERSION)" || (echo "Usage: make release VERSION=x.y.z"; exit 1)
	git tag v$(VERSION)
	git push && git push --tags
