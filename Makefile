# MCP-Frogs — convenience targets for Docker-based deployment
#
# Usage:
#   make up          — build images (if needed) and start all services
#   make down        — stop and remove containers (keep volumes)
#   make restart     — down + up
#   make build       — force-rebuild all images
#   make logs        — follow logs from all services
#   make logs-mcp    — follow logs from mcp-server only
#   make shell-mcp   — open a shell inside the mcp-server container
#   make health      — query the /health endpoint
#   make clean       — stop containers AND remove named volumes (destructive)
#   make ps          — show container status

COMPOSE         := docker compose
MCP_SERVER      := mcp-frogs-server
MCP_URL         := http://localhost:8000

.PHONY: up down restart build logs logs-mcp logs-claude \
        shell-mcp health clean ps

# ─── Lifecycle ────────────────────────────────────────────────────────────────

up:
	$(COMPOSE) up -d --remove-orphans

down:
	$(COMPOSE) down

restart: down up

build:
	$(COMPOSE) build --no-cache

# ─── Logs ────────────────────────────────────────────────────────────────────

logs:
	$(COMPOSE) logs -f

logs-mcp:
	$(COMPOSE) logs -f mcp-server

logs-claude:
	$(COMPOSE) logs -f claude-code

# ─── Shell access ─────────────────────────────────────────────────────────────

shell-mcp:
	docker exec -it $(MCP_SERVER) bash

# ─── Health check ─────────────────────────────────────────────────────────────

health:
	@curl -fs $(MCP_URL)/health | python3 -m json.tool || \
		echo "ERROR: mcp-server not reachable at $(MCP_URL)/health"

# ─── Status ───────────────────────────────────────────────────────────────────

ps:
	$(COMPOSE) ps

# ─── Cleanup (destructive) ────────────────────────────────────────────────────

clean:
	@echo "WARNING: this removes all containers AND named volumes (frogs_jobs.db will be lost)."
	@read -p "Continue? [y/N] " ans && [ "$$ans" = "y" ]
	$(COMPOSE) down -v
