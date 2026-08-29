.PHONY: setup frontend-install frontend-build run backend frontend-dev check test

PYTHON ?= python3
VENV_PYTHON := .venv/bin/python

setup:
	$(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r requirements-dev.txt
	npm --prefix frontend ci
	npm --prefix frontend run build

frontend-install:
	npm --prefix frontend ci

frontend-build:
	npm --prefix frontend run build

run: frontend-build
	$(VENV_PYTHON) -m uvicorn course_planner.api:app --host 127.0.0.1 --port 8765

backend:
	$(VENV_PYTHON) -m uvicorn course_planner.api:app --host 127.0.0.1 --port 8765 --reload

frontend-dev:
	npm --prefix frontend run dev

check:
	$(VENV_PYTHON) -m pytest -q
	$(VENV_PYTHON) -m ruff check course_planner tests
	npm --prefix frontend run check

test: check
