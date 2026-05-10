# finance_tracker_empowered_with_ai

Polymarket and precious-metals analysis toolkit with a Python codebase, connection pooling, caching, retries, and AI-assisted trade reporting.

## What This Repo Does

This repository now focuses on the backend analysis tooling only.

- Fetches and scores Polymarket markets
- Generates trade reports from live data
- Tracks gold and silver prices, including TNG eMas holdings
- Uses local Ollama analysis when available
- Writes CSV reports for later review

## Project Layout

- `python_backend/`: Python analysis scripts, utilities, and documentation

## Setup

```bash
cd python_backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python find_edge_enhanced.py
```

## Notes

- The scripts are written to run safely on Windows PowerShell.
- External API failures are handled with retries and logging.
- Generated cache and output folders are not required for source control.
