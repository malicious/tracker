venv ?= venv
activate_script = $(venv)/bin/activate

tracker_root_dir := $(dir $(realpath $(firstword $(MAKEFILE_LIST))))
flask_app := $(tracker_root_dir)tracker.app

reload_patterns := \
	$(tracker_root_dir)instance/notes-v2.db \
	$(tracker_root_dir)instance/notes-v2.db-wal \
	$(tracker_root_dir)Makefile
reload_files := $(subst $(eval ) ,:,$(reload_patterns))

.DEFAULT_GOAL := serve

.PHONY: serve-uvicorn
serve-uvicorn:
	source $(activate_script) \
  && uvicorn tracker.app_prod:asgi_app \
  --port 7529 \
  --workers 8 \
  --reload

.PHONY: serve-hypercorn
serve-hypercorn:
	source $(activate_script) \
  && hypercorn tracker.app_prod:app \
  --bind 127.0.0.1:7529 \
  --workers 4 \
  --reload

.PHONY: serve
serve:
	source $(activate_script) \
  && flask --app $(flask_app) run \
           --debug --port 7529 --with-threads \
           --extra-files $(reload_files)



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
