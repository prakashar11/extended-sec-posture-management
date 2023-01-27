#! /bin/bash

# create necessary folders

mkdir -p ./jobs
mkdir -p ./db
mkdir -p ./db/db

if [ -e nuclei-templates ]
then
   echo "reusing nuclei-templates folder"
else
   git clone https://github.com/projectdiscovery/nuclei-templates.git ./nuclei-templates
fi

# environment file for docker compose

eval "echo \"$(cat .env.start)\"" > .env

# docker build cache settings

export COMPOSE_DOCKER_CLI_BUILD=1 
export DOCKER_BUILDKIT=1 

# either build and then start container or directly build & run
# docker-compose build
docker-compose up --build
