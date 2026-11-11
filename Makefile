.PHONY: setup data test eval app

setup:
	uv sync

data:
	uv run python generate_data.py

test:
	uv run pytest

eval:
	uv run python evals/run_evals.py --runs $(or $(RUNS),1)

app:
	uv run streamlit run app.py
