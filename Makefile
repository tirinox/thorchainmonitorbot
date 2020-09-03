build:
	$(info Make: Building images.)
	docker-compose build --no-cache thtgbot redis

start:
	$(info Make: Starting containers.)
	docker-compose up -d
	docker ps

stop:
	$(info Make: Stopping containers.)
	@docker-compose stop

restart:
	$(info Make: Restarting containers.)
	@make -s stop
	@make -s start

pull:
	git pull

logs:
	docker logs -f --tail 1000 `docker ps -aqf "name=thorchainmonitorbot_thtgbot_1"`

clean:
	@docker system prune --volumes --force

upgrade:
    @make -s pull
    @make -s build
    @make -s start
