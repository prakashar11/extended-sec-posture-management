#! /bin/bash

#COMPOSE_DOCKER_CLI_BUILD=1 
export COMPOSE_DOCKER_CLI_BUILD=1 
#DOCKER_BUILDKIT=1 
export DOCKER_BUILDKIT=1 
docker-compose build
