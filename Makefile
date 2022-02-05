include .env
export

.DEFAULT_GOAL := help
.PHONY: help build start stop restart pull logs clean upgrade redis-cli redis-sv-loc

BOTNAME = thtgbot

help:
	$(info Commands: build | start | stop | restart | pull | logs | clean | upgrade | redis-cli | redis-sv-loc)

build:
	$(info Make: Building images.)
	docker-compose build --no-cache $(BOTNAME) redis

start:
	$(info Make: Starting containers.)
	@docker-compose up -d
	$(info Wait a little bit...)
	@sleep 3
	@docker ps

stop:
	$(info Make: Stopping containers.)
	@docker-compose stop

restart:
	$(info Make: Restarting containers.)
	@make -s stop
	@make -s start

poke:
	@docker-compose restart thtgbot

pull:
	@git pull

logs:
	@docker-compose logs -f --tail 1000 $(BOTNAME)

clean:
	@docker system prune --volumes --force

upgrade:
	@make -s pull
	@make -s build
	@make -s start

redis-cli:
	@redis-cli -p $(REDIS_PORT) -a $(REDIS_PASSWORD)

redis-sv-loc:
	cd redis_data
	redis-server

certbot:
	make stop
	sudo certbot certonly --standalone -w ./web/frontend -d "${DOMAIN}"
	sudo rm -rf "web/letsencrypt/${DOMAIN}/"
	sudo cp -rL "/etc/letsencrypt/live/${DOMAIN}/" letsencrypt/
	make start
