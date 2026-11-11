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

.PHONY: site-check
site-check: ## SEO tags, sitemap, robots and internal links of the built _site (run after build)
	python3 scripts/site-check.py _site --base https://thesada.io --skip 404.html

.PHONY: ci
ci: lint test build site-check ## Local CI: style, claim checks, strict Jekyll build, SEO and links

##@ Publish

# Run after the publish PR is merged and Pages has deployed; DRY=1 prints the payload only.
.PHONY: indexnow
indexnow: ## Submit the live sitemap to IndexNow (Bing and others)
	scripts/indexnow.sh https://thesada.io/sitemap.xml 0ef9ad72e19d6334c6f1fff52b14807b

##@ Housekeeping

.PHONY: clean
clean: ## Remove the Jekyll build output
	rm -rf _site .jekyll-cache

-include .forgejo/publish.mk
