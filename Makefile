# ==============================================================================
# AI Heritage Short - Orchestration Makefile
# ==============================================================================

PYTHON ?= python

ifeq ($(OS),Windows_NT)
    VENV_PYTHON = .venv/Scripts/python.exe
    RM_DIR = if exist
else
    VENV_PYTHON = .venv/bin/python
    RM_DIR = rm -rf
endif

# Fallback to system python if venv python does not exist
ACTUAL_PYTHON = $(wildcard $(VENV_PYTHON))
ifeq ($(strip $(ACTUAL_PYTHON)),)
    RUN_PY = $(PYTHON)
else
    RUN_PY = $(VENV_PYTHON)
endif

.PHONY: kaggle-pack web help install validate radio keyframes shots music film status test clean

help:
	@echo "AI Heritage Short Pipeline Commands:"
	@echo "  make install     - Install required dependencies into environment"
	@echo "  make validate    - Validate storyboard.json against schema"
	@echo "  make radio       - Generate Amharic narration & music radio-play scratch track"
	@echo "  make keyframes   - Generate visual keyframes via Cloudflare FLUX"
	@echo "  make shots       - Prepare or generate Wan 2.2 TI2V-5B video clips"
	@echo "  make music       - Prepare or generate ACE-Step 1.5 music soundtrack"
	@echo "  make film        - Orchestrate the full end-to-end filmmaking pipeline"
	@echo "  make status      - Check health of providers, credentials, and generated assets"
	@echo "  make test        - Run comprehensive test suite"
	@echo "  make kaggle-pack - Build the Kaggle upload bundle (outputs/kaggle_bundle/)"
	@echo "  make clean       - Remove cache, exports and assembly temp files"

install:
	$(RUN_PY) -m pip install -r requirements.txt

validate:
	$(RUN_PY) -m pipeline.cli validate

radio:
	@echo "Building Radio Cut (narration + ducked music). For offline mocks run: python -m pipeline.cli radio --mock"
	$(RUN_PY) -m pipeline.cli radio

keyframes:
	$(RUN_PY) -m pipeline.cli keyframes

shots:
	$(RUN_PY) -m pipeline.cli shots

music:
	$(RUN_PY) -m pipeline.cli music

film:
	$(RUN_PY) -m pipeline.cli film

status:
	$(RUN_PY) -m pipeline.cli status

test:
	$(RUN_PY) -m pytest -v tests/

kaggle-pack:
	$(RUN_PY) kaggle/bundle.py pack

clean:
	@echo "Cleaning cache and derived outputs (exports, assembly temp). Generated keyframes/shots/narration/music are kept."
	python -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ['.cache', '.pytest_cache', 'outputs/exports', 'outputs/assembly']]; print('Cleaned.')"

web:
	$(RUN_PY) -m web.server
