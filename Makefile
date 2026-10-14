# Ops Copilot - run everything in Docker.  `make help` lists the commands.
#
# First time:   make setup      (creates .env, then paste your API key into it)
#               make test       (offline checks, no key needed)
#               make run        (agent on one sample meeting)

HOST_UID := $(shell id -u 2>/dev/null || echo 1000)
HOST_GID := $(shell id -g 2>/dev/null || echo 1000)
# make run FINANCE=1 also turns on the optional finance check
AGENT_FLAGS := $(if $(FINANCE),--finance,)
export HOST_UID HOST_GID AGENT_FLAGS

COMPOSE := docker compose
RUN := $(COMPOSE) run --rm

.DEFAULT_GOAL := help
.PHONY: help setup dirs check-key need-args need-file build test run run-all evaluate approve-list approve reject push shell data clean clean-outbox

help: ## Show this help
	@echo "Ops Copilot commands:"
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  make %-13s %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make run TRANSCRIPT=data/transcripts/meeting_01_atlas_sync.txt LETTER_LANG=de"
	@echo "  make run FINANCE=1          (also check invoices for customers mentioned in the meeting)"
	@echo "  make approve SOURCE=meeting_05_month_end_finance N=6"

setup: ## Create .env from the template, then add your API key to it
	@test -f .env || (cp .env.example .env && echo "Created .env. Open it and paste your DEEPSEEK_API_KEY (or ANTHROPIC_API_KEY).")
	@mkdir -p outbox

dirs:
	@mkdir -p outbox

check-key:
	@if [ -z "$$DEEPSEEK_API_KEY$$ANTHROPIC_API_KEY" ] && ! grep -Eq '^(DEEPSEEK|ANTHROPIC)_API_KEY=.+' .env 2>/dev/null; then \
		echo "No API key found. Run 'make setup', then add your key to .env."; exit 1; fi

build: ## Build the Docker image
	$(COMPOSE) build

test: dirs build ## Run the offline checks (no API key needed)
	$(RUN) tests

run: check-key dirs build ## Run the agent on one transcript (TRANSCRIPT=..., LETTER_LANG=en|de)
	$(RUN) agent

run-all: check-key dirs build ## Run the agent on all 10 sample transcripts
	$(RUN) agent-all

evaluate: check-key dirs build ## Accuracy check on the 10 sample meetings (basic and hard sets)
	$(RUN) evaluate

approve-list: dirs build ## List drafts waiting for approval
	$(RUN) approve-list

need-args:
	@test -n "$(SOURCE)" && test -n "$(N)" || (echo "Usage: make approve SOURCE=<outbox name> N=<item number>  (run 'make approve-list' to see them)"; exit 1)

need-file:
	@test -n "$(OUTBOX_FILE)" || (echo "Usage: make push OUTBOX_FILE=outbox/<name>.json"; exit 1)

approve: need-args dirs build ## Approve a draft: make approve SOURCE=<outbox name> N=<item number>
	$(RUN) approve

reject: need-args dirs build ## Reject a draft: make reject SOURCE=<outbox name> N=<item number>
	$(RUN) -e ACTION=reject approve

push: need-file dirs build ## Push an outbox file to Notion: make push OUTBOX_FILE=outbox/<name>.json
	$(RUN) push

shell: dirs build ## Open a shell inside the container
	$(RUN) shell

data: dirs build ## Regenerate the fake invoice and payment data
	$(RUN) data

clean: ## Remove containers and the Docker image (keeps ./outbox)
	$(COMPOSE) --profile tools down --remove-orphans
	-docker image rm ops-copilot:latest

clean-outbox: ## Delete everything in ./outbox
	rm -rf outbox/*
