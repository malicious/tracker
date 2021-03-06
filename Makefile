venv ?= venv
activate_script = $(venv)/bin/activate

app := tracker.app
.DEFAULT_GOAL := serve

.PHONY: serve
serve:
	source $(activate_script) \
		&& FLASK_APP=$(app) FLASK_ENV=development flask run --port 7528



# ---------------------------------------------------------------------

.PHONY: install
install: $(activate_script)
	source $(activate_script) \
		&& pip install --requirement requirements.txt

%/bin/activate:
	-brew install pyenv
	pyenv install 3.7.5
	pyenv local 3.7.5 \
		&& eval "$(pyenv init -)" \
		&& python -m venv $*
