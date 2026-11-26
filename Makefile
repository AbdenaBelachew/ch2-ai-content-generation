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

.PHONY: web help install validate radio keyframes shots music film status test clean

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
	@echo "  make clean       - Remove cached artifacts and temporary exports"

install:
	$(RUN_PY) -m pip install -r requirements.txt

validate:
	$(RUN_PY) -m pipeline.cli validate

radio:
	@echo "Building Radio Cut (Amharic Narration + Music Scratch Mix with Ducking)..."
	$(RUN_PY) -m pipeline.cli radio --mock

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

clean:
	@echo "Cleaning output files and cache..."
	python -c "import shutil, os; [shutil.rmtree(p, ignore_errors=True) for p in ['.cache', '__pycache__']]; print('Cache cleaned.')"

web:
	$(RUN_PY) -m web.server
