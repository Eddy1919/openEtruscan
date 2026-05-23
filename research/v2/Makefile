# OpenEtruscan v2 — gold-annotation and frozen-benchmark pipelines.
#
# All paths are repo-relative; run from research/v2/ or with -C.
# Every target is idempotent: scripts append-and-resume where they can.

PY ?= python3
REPO_ROOT := $(shell git rev-parse --show-toplevel 2>/dev/null || pwd)

# Inputs (read-only, produced by v1 pipeline)
CORPUS    := $(REPO_ROOT)/research/data/openetruscan_clean.csv
SILVER    := $(REPO_ROOT)/research/data/openetruscan_labels.csv

# Outputs (produced by v2 pipeline)
DATA      := $(REPO_ROOT)/research/v2/data

# Stream A artifacts
CLF_TRAIN := $(DATA)/classify_train_pool.jsonl
CLF_TEST  := $(DATA)/classify_test_v2.jsonl
CLF_JURY  := $(DATA)/classify_jury_raw.jsonl
CLF_GOLD  := $(DATA)/classify_candidate_gold.jsonl
CLF_QUEUE := $(DATA)/classify_adjudication_queue.jsonl
CLF_SUMM  := $(DATA)/classify_jury_summary.json

# Stream B artifacts
ROS_PAIRS := $(DATA)/rosetta_pairs_raw.jsonl
ROS_EVAL  := $(DATA)/rosetta_eval_v2.jsonl
ROS_EXCL  := $(DATA)/rosetta_train_exclusions.jsonl
ROS_REPT  := $(DATA)/rosetta_contamination_report.json

# Stream C artifacts
LAC_POOL  := $(DATA)/lacuna_raw_pairs.jsonl
LAC_JURY  := $(DATA)/lacuna_jury_raw.jsonl

# Providers. Default 3-model jury, all billed to double-runway-465420-h9:
#   claude-opus-4-7 — AnthropicVertex + ADC                   (europe-west1)
#   gemini-2.5-pro  — Generative Language API, key in Secret Manager
#   llama-4-maverick — Vertex Model Garden MaaS + ADC         (us-east5)
PROVIDERS := claude-haiku-4-5 gemini-2.5-pro llama-4-maverick

.PHONY: help all check-compile classify-split classify-jury classify-adjudicate \
        rosetta-exclude lacuna-mine lacuna-jury clean

help:
	@echo "OpenEtruscan v2 pipelines"
	@echo ""
	@echo "Stream A — Classification gold"
	@echo "  make classify-split        produce frozen stratified test pool ($(CLF_TEST))"
	@echo "  make classify-jury         run multi-model LLM jury (~\$$15 in API)"
	@echo "  make classify-adjudicate   build candidate-gold + adjudication-queue"
	@echo ""
	@echo "Stream B — Rosetta-eval-v2"
	@echo "  make rosetta-exclude       verify zero train/test lemma contamination"
	@echo "                             (requires $(ROS_EVAL) and \$$CORPUS)"
	@echo ""
	@echo "Stream C — Lacunae gold"
	@echo "  make lacuna-mine           extract editor-restored inscriptions ($(LAC_POOL))"
	@echo "  make lacuna-jury           run multi-model fill-in (~\$$5-15 in API)"
	@echo ""
	@echo "Utility"
	@echo "  make check-compile         python -m py_compile every script"
	@echo "  make bootstrap-selftest    run eval/bootstrap.py's __main__"
	@echo "  make clean                 remove data/ outputs (keeps codebooks & scripts)"

check-compile:
	@cd $(REPO_ROOT) && $(PY) -m py_compile \
	    research/v2/eval/bootstrap.py \
	    research/v2/eval/classify_metrics.py \
	    research/v2/eval/rosetta_metrics.py \
	    research/v2/eval/lacuna_metrics.py \
	    research/v2/pipelines/classify_split.py \
	    research/v2/pipelines/classify_jury.py \
	    research/v2/pipelines/classify_adjudicate.py \
	    research/v2/pipelines/verify_lemma_exclusion.py \
	    research/v2/pipelines/rosetta_mine_pairs.py \
	    research/v2/pipelines/lacuna_mine.py \
	    research/v2/pipelines/lacuna_jury.py
	@echo "All scripts compile."

bootstrap-selftest:
	@cd $(REPO_ROOT) && $(PY) research/v2/eval/bootstrap.py

# --- Stream A ---------------------------------------------------------------
classify-split:
	@cd $(REPO_ROOT) && $(PY) -m research.v2.pipelines.classify_split \
	    --corpus $(CORPUS) \
	    --silver $(SILVER) \
	    --out-train $(CLF_TRAIN) \
	    --out-test  $(CLF_TEST) \
	    --n-test 400 \
	    --seed 42

classify-jury:
	@cd $(REPO_ROOT) && $(PY) -m research.v2.pipelines.classify_jury \
	    --test-pool $(CLF_TEST) \
	    --out $(CLF_JURY) \
	    --providers $(PROVIDERS) \
	    --sleep 0.5

classify-adjudicate:
	@cd $(REPO_ROOT) && $(PY) -m research.v2.pipelines.classify_adjudicate \
	    --jury $(CLF_JURY) \
	    --test-pool $(CLF_TEST) \
	    --out-gold $(CLF_GOLD) \
	    --out-queue $(CLF_QUEUE) \
	    --out-summary $(CLF_SUMM)

# --- Stream B ---------------------------------------------------------------
rosetta-exclude:
	@cd $(REPO_ROOT) && $(PY) -m research.v2.pipelines.verify_lemma_exclusion \
	    --eval $(ROS_EVAL) \
	    --corpus $(CORPUS) \
	    --out-exclusions $(ROS_EXCL) \
	    --out-report $(ROS_REPT)

# --- Stream C ---------------------------------------------------------------
lacuna-mine:
	@cd $(REPO_ROOT) && $(PY) -m research.v2.pipelines.lacuna_mine \
	    --corpus $(CORPUS) \
	    --silver-labels $(SILVER) \
	    --out $(LAC_POOL)

lacuna-jury:
	@cd $(REPO_ROOT) && $(PY) -m research.v2.pipelines.lacuna_jury \
	    --pool $(LAC_POOL) \
	    --out $(LAC_JURY) \
	    --providers $(PROVIDERS) \
	    --sleep 0.5

# --- Utility ----------------------------------------------------------------
clean:
	rm -f $(DATA)/*.jsonl $(DATA)/*.json
