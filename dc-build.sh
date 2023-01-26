#! /bin/bash

eval "echo \"$(cat .env.start)\"" > .env
export COMPOSE_DOCKER_CLI_BUILD=1 
export DOCKER_BUILDKIT=1 
# docker-compose build
docker-compose up --build
