# Check python3 version
py_version_full:=$(shell python3 --version)
py_version_major:=$(shell python3 --version | cut -d ' ' -f 2 | cut -d '.' -f 1)
py_version_minor:=$(shell python3 --version | cut -d ' ' -f 2 | cut -d '.' -f 2)

py_version_major_ok:=$(shell [ $(py_version_major) -eq 3 ] && echo true)
py_version_minor_ok:=$(shell [ $(py_version_minor) -ge 10 ] && echo true)

# define the name of the virtual environment directory
VENV := venv-fl
PYTHONPATH := $(shell pwd)

# default target, when make executed without arguments
all: venv docker_start

$(VENV)/bin/activate: requirements.txt
	python3 -m venv $(VENV)
	./$(VENV)/bin/pip3 install -r requirements.txt

ifneq ($(py_version_major_ok), true)
    	$(error "Python 3 required - $(py_version_full) found")
endif

ifneq ($(py_version_minor_ok), true)
        $(error "Python3 minor version under 10 detected $(py_version_full) found")
endif

# venv is a shortcut target
venv: $(VENV)/bin/activate

lint: venv
	./$(VENV)/bin/python3 -m pylint errol.py
	./$(VENV)/bin/python3 -m pylint src/modules/*.py
	./$(VENV)/bin/python3 -m pylint src/program/*.py
	./$(VENV)/bin/python3 -m pylint src/stages/*.py

clean:
	rm -rf $(VENV)
	find . -type f -name '*.pyc' -delete

docker_start: ./src/infra/compose.yaml ./src/infra/.env
	cd ./src/infra/; docker compose up -d

docker_stop: ./src/infra/compose.yaml
	cd ./src/infra/; docker compose down

docker_prune: docker_stop
	docker image prune
	docker network prune
	docker volume prune

.PHONY: all venv lint clean
