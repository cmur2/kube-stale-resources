
# https://tech.davis-hansson.com/p/make/
SHELL := bash
.ONESHELL:
.SILENT:
.SHELLFLAGS := -eux -o pipefail -c
.DELETE_ON_ERROR:
.DEFAULT_GOAL := all
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules

.PHONY: all
all: lint ## Run lint and test (default goal)

.PHONY: lint
lint: ## Lint all source code
	poetry run yapf -q *.py
	poetry run pylint *.py
	poetry run mypy *.py

.PHONY: help
help: ## Print this help text
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
