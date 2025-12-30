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
	docker compose build --no-cache $(BOTNAME) api redis
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
poke: # Restart only the bot container, API server and dashboard without restarting the database server.
	@docker compose restart $(BOTNAME) api dashboard
	@make -s logs


.PHONY: pull
pull: # Pull the latest changes from the repository.
	@git pull


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


.PHONY: redis-sv-loc
redis-sv-loc: # Start the Redis server locally.
	cd redis_data
	redis-server


.PHONY: certbot
certbot: # Renew the SSL certificate for the bot's web admin panel.
	docker compose stop $(BOTNAME) api nginx
	sudo certbot certonly --standalone -w ./web/frontend -d "${DOMAIN}" --email "$(LETS_ENCRYPT_EMAIL)" --agree-tos --no-eff-email
	sudo rm -rf "./web/letsencrypt/${DOMAIN}/"
	sudo cp -rL "/etc/letsencrypt/live/${DOMAIN}/" "./web/letsencrypt/${DOMAIN}"
	make start


NODE_OP_SETT_DIR = ./temp/nodeop-settings

.PHONY: buildf
buildf: # Build the frontend.
	mkdir -p ${NODE_OP_SETT_DIR}
	cd temp; git clone https://github.com/tirinox/nodeop-settings || true
	cd ${NODE_OP_SETT_DIR}; git pull
	cd ${NODE_OP_SETT_DIR}; yarn install; yarn build
	rm -rf ./web/frontend/*
	mv ${NODE_OP_SETT_DIR}/dist/* ./web/frontend/


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

.PHONY: switch-db
switch-db:	# Switch the database (see app/tools/switch-db.sh).
	cd app/tools && ./switch-db.sh


.PHONY: backup-db
backup-db: # Backup the database Redis
	cp -r ./redis_data/dump.rdb ./redis_data/dump-${DATE}.rdb


.PHONY: dashboard
dashboard:  # Run the Streamlit dashboard
	@echo "Starting Streamlit Dashboard..."
	cd $(PROJECT_ROOT)/app && PYTHONPATH="." streamlit run tools/dashboard/Dashboard.py
	#cd $(PROJECT_ROOT)/app && PYTHONPATH="." streamlit run tools/dashboard/Dashboard.py --server.fileWatcherType=all


.PHONY: redis-analysis
redis-analysis: # Run the Redis analytics tool
	docker compose exec $(BOTNAME) bash -c 'PYTHONPATH="/app" python tools/redis_analytics.py /config/config.yaml'


.PHONY: renderer-up
renderer-up: # Launch the HTML renderer image
	docker compose up -d renderer


.PHONY: renderer-dev
renderer-dev: # Launch the HTML renderer image in development mode
	cd app && uvicorn renderer.worker:app --port 8404 --reload


.PHONY: auth-twitter
auth_twitter: # Authenticate your Twitter handle to be managed by the bot.
	cd app && PYTHONPATH=. python tools/auth_twitter.py


.PHONY: auth-twitter-docker
auth_twitter_docker: # Authenticate your Twitter handle to be managed by the bot (with Docker, without Python env)
	docker build -f Dockerfile-twitter-auth -t thor_bot_twitter_auth .
	docker run -it -v ./app:/app -v ./config.yaml:/config/config.yaml thor_bot_twitter_auth


.PHONY: thin-out-pool-cache  # Thin out the pool cache
thin-out-pool-cache:
	docker compose exec $(BOTNAME) bash -c 'PYTHONPATH="/app" python tools/thin_out_pool_cache.py /config/config.yaml'


.PHONY: fill-pool-cache  # Fill the pool cache
fill-pool-cache:
	docker compose exec $(BOTNAME) bash -c 'PYTHONPATH="/app" python tools/fill_pool_cache.py /config/config.yaml'


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