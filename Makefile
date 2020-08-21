
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

.PHONY: e2e-with-kind
e2e-with-kind: ## Run E2E tests against running kind (K8s in Docker) instance
	function cleanup {
	  (kubectl delete namespace e2e || true)
	}
	trap cleanup EXIT

	# no resources and empty cluster should have no stale resources
	poetry run python kube-stale-resources.py --blacklist e2e/blacklist-kind-empty.txt -f e2e/resources-kind-empty.yml

	# some resources in VCS and empty cluster should have no stale resources
	kubectl apply -f e2e/resources-kind-one.yml
	poetry run python kube-stale-resources.py --blacklist e2e/blacklist-kind-empty.txt -f e2e/resources-kind-one.yml
	cleanup

	# some resources NOT in VCS and empty cluster should have stale resources
	kubectl apply -f e2e/resources-kind-one.yml
	(poetry run python kube-stale-resources.py --blacklist e2e/blacklist-kind-empty.txt -f e2e/resources-kind-empty.yml && exit 1 || exit 0)
	cleanup

.PHONY: help
help: ## Print this help text
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
