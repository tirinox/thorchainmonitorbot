include .env
export

BOTNAME = thtgbot
DATE = $(shell date +'%Y-%m-%d-%H-%M-%S')
PROJECT_ROOT := $(shell git rev-parse --show-toplevel 2>/dev/null || pwd)


default: help

.PHONY: help
help: # Show help for each of the Makefile recipes.
	@grep -E '^[a-zA-Z0-9 -]+:.*#'  Makefile | sort | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#')\n"; done


.PHONY: attach
attach: # Attach to the bot container.
	docker compose exec $(BOTNAME) bash


.PHONY: build
build: # Build images.
	$(info Make: Building images.)
	docker compose build --no-cache $(BOTNAME) api redis dashboard
	echo "Note! Use 'make start' to make the changes take effect (recreate containers with updated images)."


.PHONY: start
start: # Start containers.
	$(info Make: Starting containers.)
	@docker compose up -d
	$(info Wait a little bit...)
	@sleep 3
	@docker ps


.PHONY: stop
stop: # Stop containers.
	$(info Make: Stopping containers.)
	@docker compose stop


.PHONY: restart
restart: # Restart containers.
	$(info Make: Restarting containers.)
	@make -s stop
	@make -s start


.PHONY: poke
poke: # Restart only the bot container, API server, renderer and dashboard without restarting the database server.
	git pull
	@docker compose restart $(BOTNAME) api renderer dashboard nginx
	@make -s logs


.PHONY: pull
pull: # Pull the latest changes from the repository.
	@git pull



.PHONY: merge-develop-into-main
merge-develop-into-main: # Merge develop into main, push main, and switch back to develop.
	git fetch origin && \
	git switch main && \
	git pull --ff-only origin main && \
	git merge develop && \
	git push origin main && \
	git switch develop


.PHONY: logs
logs: # Show logs.
	@docker compose logs -f --tail 1000 $(BOTNAME)


.PHONE: dump-logs
dump-logs: # Dump logs to logs.txt.
	echo "Dumping logs to logs.txt..."
	@docker compose logs --tail 180000 $(BOTNAME) > logs.txt


.PHONY: clean
clean: # Remove containers and volumes.
	@docker system prune --volumes --force


.PHONY: upgrade
upgrade: # Pull, build, and start.
	@make -s pull
	@make -s build
	@make -s start


.PHONY: redis-cli
redis-cli: # Connect to the Redis CLI.
	@redis-cli -p $(REDIS_PORT) -a $(REDIS_PASSWORD)


.PHONY: keydb-cli
keydb-cli: # Connect to the KeyDB CLI.
	@docker compose exec keydb keydb-cli -p $(KEYDB_PORT) -a $(KEYDB_PASSWORD)


.PHONY: redis-sv-loc
redis-sv-loc: # Start the Redis server locally.
	cd redis_data
	redis-server


.PHONY: certbot
certbot: # Issue the SSL certificate for the first time (renewals then run in the certbot container).
	docker compose stop nginx
	docker compose run --rm -p 80:80 --entrypoint certbot certbot certonly --standalone -d "${DOMAIN}" --email "$(LETS_ENCRYPT_EMAIL)" --agree-tos --no-eff-email
	docker compose up -d nginx certbot


.PHONY: certbot-test
certbot-test: # Dry-run a certificate renewal through the nginx webroot.
	docker compose run --rm --entrypoint certbot certbot renew --webroot -w /var/www/certbot --dry-run


NODE_OP_SETT_REPO = https://github.com/tirinox/nodeop-settings
NODE_OP_SETT_DIR = ./temp/nodeop-settings
FRONTEND_DIR = ./web/frontend
FRONTEND_PREV_DIR = ./temp/frontend-prev

.PHONY: frontend-build
frontend-build: # Pull nodeop-settings, build it in a Node container (no Node on the host) and deploy to web/frontend.
	mkdir -p temp
	[ -d ${NODE_OP_SETT_DIR}/.git ] || git clone ${NODE_OP_SETT_REPO} ${NODE_OP_SETT_DIR}
	cd ${NODE_OP_SETT_DIR} && git pull --ff-only && git log -1 --format='Building %h %ci %s'
	cd ${NODE_OP_SETT_DIR} && rm -rf dist && docker run --rm -u "$$(id -u):$$(id -g)" -e npm_config_cache=/tmp/.npm \
		-v "$$PWD":/app -w /app node:$$(cat .nvmrc 2>/dev/null || echo 22)-alpine \
		sh -c "npm ci --no-audit --no-fund && npm run build"
	test -f ${NODE_OP_SETT_DIR}/dist/index.html
	rm -rf ${FRONTEND_PREV_DIR} && mkdir -p ${FRONTEND_PREV_DIR} && cp -a ${FRONTEND_DIR}/. ${FRONTEND_PREV_DIR}/
	find ${FRONTEND_DIR} -mindepth 1 ! -name .gitignore -delete
	cp -a ${NODE_OP_SETT_DIR}/dist/. ${FRONTEND_DIR}/
	echo "Frontend deployed; nginx serves it right away. Previous version: ${FRONTEND_PREV_DIR} (make frontend-rollback)."

.PHONY: buildf
buildf: frontend-build # Alias for frontend-build.

.PHONY: frontend-rollback
frontend-rollback: # Restore web/frontend from the copy saved by the last frontend-build.
	test -f ${FRONTEND_PREV_DIR}/index.html
	find ${FRONTEND_DIR} -mindepth 1 ! -name .gitignore -delete
	cp -a ${FRONTEND_PREV_DIR}/. ${FRONTEND_DIR}/


.PHONY: test
test: # Run tests.
	cd app && python -m pytest tests


.PHONY: lint
lint: # Run linters.
	find ./app/services -type f -name "*.py" | xargs pylint
	find ./app/localization -type f -name "*.py" | xargs pylint

.PHONY: graph
graph: # Generate a graph of the bot internal structure.
	cd app && python graph.py


.PHONY: mimir-add-word
mimir-add-word: # Run the interactive Mimir naming dictionary updater.
	cd app && PYTHONPATH="." python tools/mimir_add_word.py

.PHONY: switch-db
switch-db:	# Switch the database (see app/tools/switch-db.sh).
	cd app/tools && ./switch-db.sh


.PHONY: backup-db
backup-db: # Backup the database Redis
	cp -r ./redis_data/dump.rdb ./redis_data/dump-${DATE}.rdb


.PHONY: dashboard-dev
dashboard-dev:  # Run the dashboard API locally with auto-reload (pair with dashboard-front-dev)
	@echo "Stopping the dashboard container if it's running..."
	docker compose stop dashboard
	cd $(PROJECT_ROOT)/app && PYTHONPATH="." python dashboard_api.py ../config.yaml --reload


.PHONY: dashboard-front-dev
dashboard-front-dev:  # Run the dashboard Vue frontend with hot reload at http://localhost:5173/dashboard/
	cd $(PROJECT_ROOT)/web/dashboard && npm install && npm run dev


.PHONY: dashboard-build
dashboard-build:  # Build the dashboard frontend into web/dashboard/dist (served by dashboard_api.py)
	cd $(PROJECT_ROOT)/web/dashboard && npm ci && npm run build


.PHONY: redis-analysis
redis-analysis: # Run the Redis analytics tool
	docker compose exec $(BOTNAME) bash -c 'PYTHONPATH="/app" python tools/redis_analytics.py /config/config.yaml'
	@echo "------------------------------"
	docker compose exec redis redis-cli -p $(REDIS_PORT) -a $(REDIS_PASSWORD) --memkeys


.PHONY: backup-keydb
backup-keydb: # Copy the KeyDB dump (pool history cache) to a dated file next to it.
	cp ./keydb_data/dump.rdb ./keydb_data/dump-${DATE}.rdb


.PHONY: renderer-up
renderer-up: # Launch the HTML renderer image
	docker compose up -d renderer


.PHONY: renderer-dev
renderer-dev: # Launch the HTML renderer locally in development mode
	cd app && PYTHONPATH=. uvicorn renderer.main_renderer:app --port 8404 --reload


.PHONY: renderer-demos
renderer-demos: # Regenerate the achievement demos for the renderer gallery (http://127.0.0.1:8404/render/demo)
	cd app && PYTHONPATH=. python tools/gen_achievement_demos.py


.PHONY: renderer-restart
renderer-restart: # Restart the renderer container to pick up template and engine changes
	@docker compose restart renderer
	@docker compose logs -f --tail 100 renderer


.PHONY: auth-twitter
auth_twitter: # Authenticate your Twitter handle to be managed by the bot.
	cd app && PYTHONPATH=. python tools/auth_twitter.py


.PHONY: auth-twitter-docker
auth_twitter_docker: # Authenticate your Twitter handle to be managed by the bot (with Docker, without Python env)
	docker build -f Dockerfile-twitter-auth -t thor_bot_twitter_auth .
	docker run -it -v ./app:/app -v ./config.yaml:/config/config.yaml thor_bot_twitter_auth


.PHONY: restore-vote-data
restore-vote-data: # Restore vote records from past blocks (interactive prompts for days/interval/concurrency)
	docker compose exec -it $(BOTNAME) bash -c 'PYTHONPATH="/app" python tools/restore_vote_data.py'


MIN_DISTANCE ?= 10

.PHONY: thin-out-pool-cache
thin-out-pool-cache: # Thin out the pool history cache in KeyDB (MIN_DISTANCE=10 blocks; YES=1 skips the question; DRY_RUN=1 only counts).
	docker compose exec $(BOTNAME) bash -c 'PYTHONPATH="/app" python tools/thin_out_pool_cache.py /config/config.yaml \
		--min-distance $(MIN_DISTANCE) $(if $(YES),--yes) $(if $(DRY_RUN),--dry-run)'


.PHONY: fill-pool-cache  # Fill the pool cache
fill-pool-cache:
	docker compose exec $(BOTNAME) bash -c 'PYTHONPATH="/app" python tools/fill_pool_cache.py /config/config.yaml'


.PHONY: migrate-pool-cache-to-keydb  # Migrate pool cache from Redis to KeyDB and optionally flush old Redis key
migrate-pool-cache-to-keydb:
	docker compose exec -it $(BOTNAME) bash -c 'PYTHONPATH="/app" python tools/migrate_pool_cache_redis_to_keydb.py /config/config.yaml'


.PHOHY: web-auth-add-user  # Add new web auth user
web-auth-add-user:
	# ask username and password and store them in htpasswd-dash-logs
	@printf "Username: "; read USER; \
	printf "Password: "; stty -echo; read PASS; stty echo; echo ""; \
	if [ ! -f web/htpasswd-dash-logs ]; then \
		echo "Creating web/htpasswd-dash-logs ..."; \
		htpasswd -bc web/htpasswd-dash-logs $$USER $$PASS; \
	else \
		echo "Updating web/htpasswd-dash-logs ..."; \
		htpasswd -b web/htpasswd-dash-logs $$USER $$PASS; \
	fi


.PHONY: deploy-poke  # Deploy the bot (pull, build, and restart)
deploy-poke:
	ssh $(DEPLOY_SSH) "cd $(DEPLOY_PATH) && git pull && make poke"
