UID := $(shell id -u)
GID := $(shell id -g)
PWD = $(shell pwd)

LOCAL_DIR = $(PWD)/core/venv/bin
PYTHON = $(LOCAL_DIR)/python
PYTHON3 = python3.10
PIP_SYNC = $(PYTHON) -m piptools sync --python-executable $(PYTHON)
PIP_COMPILE = $(PYTHON) -m piptools compile --strip-extras

args=
# if dockerfile is not defined
ifndef dockerfile
	dockerfile=compose.yml
endif

docker-compose-files=-f ${dockerfile}

run_in_docker=docker compose ${docker-compose-files} exec php-web

help:  ## Show help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m\033[0m\n"} /^[$$()% a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

# build docker images for all docker-compose files
build:  ## Build docker images
	docker compose $(docker-compose-files) build

build-no-cache:  ## Build docker images without cache
	docker compose $(docker-compose-files) --compatibility build --no-cache

up:  ## Start docker containers
	docker compose ${docker-compose-files} up -d ${args}

down:  ## Stop docker containers
	docker compose ${docker-compose-files} down

stop:  ## Stop docker containers
	docker compose ${docker-compose-files} stop

restart:  ## Restart service [service=php]
	docker compose ${docker-compose-files} restart

test:  ## Run tests
	docker exec cheshire_cat_core python -m pytest --color=yes -vvv -W ignore -x ${args}

sync-requirements: ## Update the local virtual environment with the latest requirements.
	@cd core && $(PYTHON) -m pip install --upgrade pip-tools pip wheel
	@cd core && $(PIP_SYNC) requirements.txt
	@cd core && $(PYTHON) -m pip install -r requirements.txt
	@cd ..

compile-requirements: ## Compile requirements for the local virtual environment.
	@cd core && $(PYTHON) -m pip install --upgrade pip-tools pip wheel
	@cd core && $(PIP_COMPILE) --no-upgrade --output-file requirements.txt pyproject.toml

update-requirements: ## Compile requirements for the local virtual environment.
	@cd core && $(PIP_COMPILE) --upgrade --output-file requirements.txt pyproject.toml
