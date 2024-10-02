include .env
export

BOTNAME = thtgbot
DATE = $(shell date +'%Y-%m-%d-%H-%M-%S')

default: help

.PHONY: help
help: # Show help for each of the Makefile recipes.
	@grep -E '^[a-zA-Z0-9 -]+:.*#'  Makefile | sort | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#')\n"; done


.PHONY: attach
attach: # Attach to the bot container.
	docker-compose exec $(BOTNAME) bash

.PHONY: build
build: # Build images.
	$(info Make: Building images.)
	docker-compose build --no-cache $(BOTNAME) api redis
	echo "Note! Use 'make start' to make the changes take effect (recreate containers with updated images)."

.PHONY: start
start: # Start containers.
	$(info Make: Starting containers.)
	@docker-compose up -d
	$(info Wait a little bit...)
	@sleep 3
	@docker ps

.PHONY: stop
stop: # Stop containers.
	$(info Make: Stopping containers.)
	@docker-compose stop

.PHONY: restart
restart: # Restart containers.
	$(info Make: Restarting containers.)
	@make -s stop
	@make -s start

.PHONY: poke
poke: # Restart the bot.
	@docker-compose restart $(BOTNAME) api
	@make -s logs

.PHONY: pull
pull: # Pull the latest changes from the repository.
	@git pull

.PHONY: logs
logs: # Show logs.
	@docker-compose logs -f --tail 1000 $(BOTNAME)

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
	docker-compose stop $(BOTNAME) api nginx
	sudo certbot certonly --standalone -w ./web/frontend -d "${DOMAIN}"
	# todo: fix paths!
	sudo rm -rf "./web/letsencrypt/${DOMAIN}/"
	sudo cp -rL "/etc/letsencrypt/live/${DOMAIN}/*" "./web/letsencrypt/"
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


.PHONE: dashboard
dashboard: # Start the dashboard
	cd app && streamlit run dashboard.py
