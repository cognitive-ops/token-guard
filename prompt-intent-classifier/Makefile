# Prompt-intent classifier — offline build pipeline.
# Run from this directory; all scripts read/write ./data (gitignored).
#
#   make prep    -> gather prompts + submit labeling batch
#   (wait for the Anthropic batch to finish — minutes to hours)
#   make model   -> fetch labels + train + export the ONNX model
#   make deploy  -> publish the model bundle (then commit deploy-model/ via Git LFS)

.ONESHELL:
.PHONY: help setup data prep model deploy
.DEFAULT_GOAL := help

ENV := set -a; . ../.env; set +a   # load ANTHROPIC_API_KEY from repo-root .env

# Trainer for `make model`. Default coarse_mt matches the committed deploy-model/
# bundle (v5, xlm-roberta, 5-way coarse intents — what export_onnx.py auto-detects first).
# Override e.g. TRAIN_SCRIPT=train_ft3.py for the 7-way fine model.
TRAIN_SCRIPT ?= train_coarse_mt.py

# Checkpoint to export. Empty = export_onnx.py auto-detects (coarse_mt, then ft3/ft).
# Set when overriding TRAIN_SCRIPT, e.g. EXPORT_MODEL=data/model_ft3_distilbert-base-multilingual-cased.pt
EXPORT_MODEL ?=

help: ## show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | column -t -s '	'

setup: ## create venv and install deps
	python -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt

data: ## run the DVC data pipeline: merge raw -> clean/dedup -> gitleaks-scrub -> data/processed/labelable.jsonl
	dvc repro
	@echo "labelable set (secret-free): data/processed/labelable.jsonl"

prep: ## extract prompts from Loki + submit the labeling batch (needs Loki + API key)
	python src/extract_prompts.py
	$(ENV); python src/label_batch.py submit

model: ## fetch labels, train, export to ONNX, tune behavior thresholds (after batch finishes)
	$(ENV); python src/label_batch.py fetch
	python src/$(TRAIN_SCRIPT)
	python src/export_onnx.py $(EXPORT_MODEL)
	python src/tune_thresholds.py $(EXPORT_MODEL)

deploy: ## copy the exported bundle into deploy-model/ (then: git add + commit via LFS)
	cp data/onnx/model.int8.onnx data/onnx/tokenizer.json data/onnx/meta.json deploy-model/
	@echo "Updated deploy-model/. Review, then: git add deploy-model && git commit"
