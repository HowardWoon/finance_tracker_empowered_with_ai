# Market Intelligence Toolkit

Market intelligence and metals analysis toolkit with a Python backend, connection pooling, caching, retries, and AI-assisted reporting.

## Purpose

This repository is focused on one thing: generating actionable analysis from live market and metals data.

- Fetches and scores Polymarket markets
- Produces trade reports from live data
- Tracks gold and silver prices, including a personal reference position
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
