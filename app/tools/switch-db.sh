#!/bin/bash

set -e
# Get the PID of the Redis server
redis_pid=$(pgrep redis-server)

if [ -z "$redis_pid" ]; then
  echo "Redis server is not running."
else
  echo "Stopping Redis server (PID: $redis_pid)..."
  kill "$redis_pid"

  # Wait for the process to exit
  while ps -p "$redis_pid" > /dev/null; do
    sleep 1
  done

  echo "Redis server with PID $redis_pid has gracefully exited."
fi

cd "../../redis_data" || exit
mv dump.rdb dump.rdb.temp
mv dump.rdb.bak dump.rdb
mv dump.rdb.temp dump.rdb.bak

ls -lah

redis-server
echo "Redis server started."
