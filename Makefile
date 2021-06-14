venv ?= venv
activate_script = $(venv)/bin/activate

app := tracker.app
.DEFAULT_GOAL := serve

.PHONY: serve
serve: instance/tasks.db
	source $(activate_script) \
		&& FLASK_APP=$(app) FLASK_ENV=development flask run --port 7528



# ---------------------------------------------------------------------

.PHONY: force-test-migration
force-test-migration: $(activate_script) instance/tasks.db
	source $(activate_script) \
		&& FLASK_APP=$(app) FLASK_ENV=development flask t2-migrate

.PHONY: install
install: $(activate_script)
	source $(activate_script) \
		&& pip install --upgrade pip \
		&& pip install --requirement requirements.txt

instance/%.db: instance/%.sql
	-sqlite3 $@ < $<

%/bin/activate:
	-brew install pyenv
	-pyenv install 3.7.5
	pyenv local 3.7.5 \
		&& eval "`pyenv init -`" \
		&& python -m venv $*
	echo "" >> $@
	echo "export FLASK_APP=$(app)" >> $@
	echo "export FLASK_ENV=development" >> $@
