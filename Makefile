# MCP-Frogs — convenience targets for Docker-based deployment
#
# Default mode: all-in-one container (Claude Code + MCP server + FROGS envs)
#
#   make build    — build the all-in-one image
#   make run      — start MCP server + launch Claude Code (interactive)
#   make shell    — start MCP server + open a debug bash shell
#   make health   — query the /health endpoint from the host
#   make logs     — follow logs from a running all-in-one container
#   make clean    — stop containers AND remove named volumes (destructive)
#   make ps       — show container status
#
# Two-container mode (alternative, --profile multi):
#
#   make multi-build   — build mcp-server and claude-code images
#   make multi-up      — start mcp-server in the background
#   make multi-run     — run claude-code connected to mcp-server
#   make multi-down    — stop all multi-profile containers
#   make multi-logs    — follow logs from all multi-profile containers
#   make multi-logs-mcp — follow logs from mcp-server only
#   make multi-shell-mcp — open a shell inside mcp-frogs-server

COMPOSE         := docker compose
CONTAINER       := mcp-frogs
MCP_URL         := http://localhost:8000

.PHONY: build run shell health logs clean ps \
        multi-build multi-up multi-run multi-down multi-logs multi-logs-mcp multi-shell-mcp

# ─── All-in-one (default) ─────────────────────────────────────────────────────

build:
	$(COMPOSE) build all-in-one

run:
	$(COMPOSE) run --rm all-in-one claude

shell:
	$(COMPOSE) run --rm all-in-one bash

health:
	@curl -fs $(MCP_URL)/health | python3 -m json.tool || \
		echo "ERROR: MCP server not reachable at $(MCP_URL)/health"

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

clean:
	@echo "WARNING: this removes all containers AND named volumes (frogs_jobs.db will be lost)."
	@read -p "Continue? [y/N] " ans && [ "$$ans" = "y" ]
	$(COMPOSE) --profile multi down -v
	$(COMPOSE) down -v

# ─── Two-container setup (alternative) ────────────────────────────────────────

multi-build:
	$(COMPOSE) --profile multi build

multi-up:
	$(COMPOSE) --profile multi up -d --remove-orphans mcp-server

multi-run:
	$(COMPOSE) --profile multi run --rm claude-code claude

multi-down:
	$(COMPOSE) --profile multi down

multi-logs:
	$(COMPOSE) --profile multi logs -f

multi-logs-mcp:
	$(COMPOSE) --profile multi logs -f mcp-server

multi-shell-mcp:
	docker exec -it mcp-frogs-server bash
