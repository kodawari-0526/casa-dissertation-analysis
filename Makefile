.PHONY: dry-run run test check

dry-run:
	python run_pipeline.py --dry-run

run:
	python run_pipeline.py

test:
	python -m pytest -q

check:
	python -m compileall -q run_pipeline.py src tests
	python -m pytest -q
