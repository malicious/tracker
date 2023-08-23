venv ?= venv
activate_script = $(venv)/bin/activate

app := tracker.app
.DEFAULT_GOAL := serve

.PHONY: serve
serve:
	source $(activate_script) \
		&& flask --app $(app) --debug run \
		   --port 7529 --with-threads



# ---------------------------------------------------------------------

.PHONY: install
install: $(activate_script)
	source $(activate_script) \
		&& pip install --upgrade pip \
		&& pip install --requirement requirements.txt

%/bin/activate:
	-brew install pyenv
	-pyenv install 3.11.3
	pyenv local 3.11.3 \
		&& eval "`pyenv init -`" \
		&& python -m venv $*
