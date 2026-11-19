.PHONY: setup run check browser

PYTHON ?= python3
VENV_PYTHON = .venv/bin/python

# Development only; leave production DATABASE_URL/secrets out of this shell.
setup:
	$(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install -r requirements-dev.txt
	$(VENV_PYTHON) manage.py migrate --noinput
	$(VENV_PYTHON) manage.py collectstatic --noinput
	$(VENV_PYTHON) manage.py check

run:
	$(VENV_PYTHON) manage.py runserver 127.0.0.1:8000 --noreload

check:
	$(VENV_PYTHON) manage.py test --noinput
	$(VENV_PYTHON) manage.py makemigrations --check --dry-run
	$(VENV_PYTHON) -m pip check
	node --test deploy/cloudflare/worker.test.mjs
	node --test deploy/preview/worker.test.mjs

browser:
	$(VENV_PYTHON) manage.py collectstatic --noinput
	$(VENV_PYTHON) scripts/check_browser.py
