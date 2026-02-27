IMAGE   := personal-finance
PORT    := 8501
CONTAINER := finance

.PHONY: help build run stop logs restart shell clean dev

## ── Help ─────────────────────────────────────────────────────────────────────
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

## ── Docker ───────────────────────────────────────────────────────────────────
build: ## Build the Docker image
	docker build -t $(IMAGE) .

build-no-cache: ## Build the Docker image from scratch (no layer cache)
	docker build --no-cache -t $(IMAGE) .

run: ## Run the container (mounts secrets, exposes port $(PORT))
	docker run -d \
		--name $(CONTAINER) \
		-p $(PORT):8501 \
		-v "$(PWD)/.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro" \
		-v "$(PWD)/.secret:/app/.secret:ro" \
		$(IMAGE)
	@echo "Dashboard → http://localhost:$(PORT)"

stop: ## Stop and remove the container
	docker stop $(CONTAINER) && docker rm $(CONTAINER)

restart: stop run ## Restart the container

logs: ## Tail container logs
	docker logs -f $(CONTAINER)

shell: ## Open a shell inside the running container
	docker exec -it $(CONTAINER) /bin/bash

clean: ## Remove the Docker image
	docker rmi $(IMAGE)

## ── Local dev (no Docker) ────────────────────────────────────────────────────
dev: ## Run the app locally with uv
	uv run streamlit run main.py
