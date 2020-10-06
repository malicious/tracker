venv := venv
app := tracker.app

.DEFAULT_GOAL := serve

.PHONY: serve
serve:
	source $(venv)/bin/activate \
		&& FLASK_APP=$(app) FLASK_ENV=development flask run --port 7528

# ---------------------------------------------------------------------

.PHONY: install
install: $(venv)/bin/activate
	source $(venv)/bin/activate \
		&& pip install flask

$(venv)/bin/activate:
	-brew install pyenv
	pyenv install 3.7.5
	pyenv local 3.7.5 \
		&& eval "$(pyenv init -)" \
		&& python3 -m venv $(venv)
