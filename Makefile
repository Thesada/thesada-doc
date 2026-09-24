# thesada-doc. Bare `make` prints this list and changes nothing.
# No fmt target: the site has a style gate, not a rewriter.
.DEFAULT_GOAL := help
SHELL := bash

##@ General

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nusage: make <target>\n"} \
	  /^[a-zA-Z0-9_.-]+:.*##/ { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 } \
	  /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)

##@ Setup

.PHONY: setup
setup: ## Install the Jekyll gems into a clean clone
	bundle install

##@ Build

.PHONY: build
build: ## Build the site the way CI does, strict front matter
	bundle exec jekyll build --strict_front_matter --trace

.PHONY: run
run: ## Serve the site locally
	bundle exec jekyll serve

##@ Test

.PHONY: test
test: ## Prove the claim comments against the firmware and app source
	python3 scripts/check-spec-drift.py

.PHONY: lint
lint: ## Em dashes and the other style rules
	scripts/check-style.sh

##@ Housekeeping

.PHONY: clean
clean: ## Remove the Jekyll build output
	rm -rf _site .jekyll-cache
