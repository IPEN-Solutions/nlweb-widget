uv python install 3.10
uv venv --python 3.10
.\.venv\Scripts\Activate.ps1
uv sync --dev --all-extras
uv run pytest
uv run ruff check .
uv build
