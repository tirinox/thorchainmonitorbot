build:
	$(info Make: Building images.)
	docker-compose build --no-cache thtgbot redis

start:
	$(info Make: Starting containers.)
	docker-compose up -d
	docker ps

bs:
	@make -s build
	@make -s start

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
	docker logs -f --tail 1000 `docker ps -aqf "name=thtgbot"`

clean:
	@docker system prune --volumes --force