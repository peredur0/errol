# Check python3 version
py_version_full:=$(shell python3 --version)
py_version_major:=$(shell python3 --version | cut -d ' ' -f 2 | cut -d '.' -f 1)
py_version_minor:=$(shell python3 --version | cut -d ' ' -f 2 | cut -d '.' -f 2)

py_version_major_ok:=$(shell [ $(py_version_major) -eq 3 ] && echo true)
py_version_minor_ok:=$(shell [ $(py_version_minor) -ge 10 ] && echo true)

# define the name of the virtual environment directory
VENV := ia-venv
PYTHONPATH := $(shell pwd)

# default target, when make executed without arguments
all: venv

$(VENV)/bin/activate: requirements.txt
	python3 -m venv $(VENV)
	./$(VENV)/bin/pip3 install -r requirements.txt

ifneq ($(py_version_major_ok), true)
    	$(error "Python 3 required - $(py_version_full) found")
endif

ifneq ($(py_version_minor_ok), true)
        $(error "Python3 minor version under 11 detected $(py_version_full) found")
endif

# venv is a shortcut target
venv: $(VENV)/bin/activate

clean:
	rm -rf $(VENV)
	find . -type f -name '*.pyc' -delete

.PHONY: all venv lint clean
