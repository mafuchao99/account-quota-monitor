CONFIG ?= config.yaml
LOG_LEVEL ?= DEBUG

.PHONY: setup install run collect report test clean

setup:
	uv run python scripts/dev.py setup

install:
	uv run python scripts/dev.py setup

run:
	uv run python scripts/dev.py run --config $(CONFIG) --log-level $(LOG_LEVEL)

collect:
	uv run python scripts/dev.py collect --config $(CONFIG) --log-level $(LOG_LEVEL)

report:
	uv run python scripts/dev.py report --config $(CONFIG) --log-level $(LOG_LEVEL)

test:
	uv run python scripts/dev.py test

clean:
	uv run python scripts/dev.py clean
