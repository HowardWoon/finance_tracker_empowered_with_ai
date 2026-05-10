# finance_tracker_empowered_with_ai

Personal finance tracker with a Flutter frontend and a Python backend for market analysis, gold tracking, and AI-assisted insights.

## What This Repo Does

This repository combines two parts:

- A Flutter app for tracking transactions and viewing finance data
- A Python backend for Polymarket edge detection, gold/silver monitoring, and automated report generation

## Main Features

- Track income and expenses inside the Flutter app
- Connect to AI-powered analysis through the backend
- Fetch live Polymarket market data and produce trade ideas
- Monitor gold and silver prices with personal TNG eMas holdings
- Save generated reports to CSV for later review

## Project Layout

- `lib/`: Flutter app code
- `python_backend/`: Python analysis scripts, utilities, and documentation
- `android/`, `web/`, `test/`: Flutter platform and test folders

## Setup

### Flutter app

```bash
flutter pub get
flutter run
```

### Python backend

```bash
cd python_backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python find_edge_enhanced.py
```

## Notes

- The backend scripts are written to run safely on Windows PowerShell.
- External API failures are handled with retries and logging.
- The repo intentionally keeps only the current finance tracker implementation and related backend code.
