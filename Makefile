install:
	pip install uv
	uv sync

dev:
	@echo "Starting server with local .env"
	@uv run uvicorn app.main:app --reload --port 8000 --loop uvloop

# Evaluation commands
eval:
	@echo "Running evaluation with interactive mode"
	@python -m evals.main --interactive

eval-quick:
	@echo "Running evaluation with default settings"
	@python -m evals.main --quick

eval-no-report:
	@echo "Running evaluation without generating report"
	@python -m evals.main --no-report

lint:
	ruff check .

format:
	ruff format .

clean:
	rm -rf .venv
	rm -rf __pycache__
	rm -rf .pytest_cache

# Help
help:
	@echo "Usage: make <target>"
	@echo "Targets:"
	@echo "  install: Install dependencies"
	@echo "  dev: Run server with local .env"
	@echo "  eval: Run evaluation with interactive mode"
	@echo "  eval-quick: Run evaluation with default settings"
	@echo "  eval-no-report: Run evaluation without generating report"
	@echo "  test: Run tests"
	@echo "  clean: Clean up"