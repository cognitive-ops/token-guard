# Prompt-intent classifier — offline build pipeline.
# Run from this directory; all scripts read/write ./data (gitignored).
#
#   python src/extract_prompts_full.py -> python src/label.py run   (manual, see dvc.yaml header)
#   make data     -> dvc repro: clean -> scrub -> train -> export+tune ONNX
#   make deploy   -> publish the model bundle (then commit deploy-model/ via Git LFS)
#
# train/export are now dvc.yaml stages (not duplicated here) so `dvc repro` is the
# single source of truth for what reruns when a dep changes.

.ONESHELL:
.PHONY: help setup data prep deploy
.DEFAULT_GOAL := help

ENV := set -a; . ../.env; set +a   # load ANTHROPIC_API_KEY from repo-root .env

help: ## show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | column -t -s '	'

setup: ## create venv and install deps
	python -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt

data: ## run the full DVC pipeline: clean -> scrub -> train -> export+tune (needs data/processed/labeled.jsonl already labeled — see dvc.yaml)
	dvc repro
	@echo "onnx bundle: data/onnx/{model.int8.onnx,tokenizer.json,meta.json}"

prep: ## ALTERNATE labeling path: extract from Loki + submit a Batch-API labeling job (50% off, for large corpora; async — see label_batch.py fetch)
	python src/extract_prompts.py
	$(ENV); python src/label_batch.py submit

deploy: ## copy the exported bundle into deploy-model/ (then: git add + commit via LFS)
	cp data/onnx/model.int8.onnx data/onnx/tokenizer.json data/onnx/meta.json deploy-model/
	@echo "Updated deploy-model/. Review, then: git add deploy-model && git commit"
