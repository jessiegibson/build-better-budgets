# Budgeting App

A comprehensive Python-based application for importing, consolidating, classifying, and analyzing financial transactions. Designed for personal budgeting, tax deduction tracking, and goal management, it supports multiple data formats (CSV, PDF, QFX), offers a machine learning-driven categorization system, and features both a CLI and a full-featured web interface.

---

## Features

- Ingest transactions from CSV, PDF, and QFX (Quicken) formats
- Detect and normalize formats for major institutions (e.g., Chase, Amex, Discover)
- Consolidate and de-duplicate transactions into a single unified SQLite database
- ML-driven classification with interactive feedback and training loop
- Track real estate expenses, Section 179 equipment, recurring charges, and tax-deductible purchases
- Generate budgets, forecasts, and financial goals
- Create reports for tax filing and expense analysis
- Web interface for browsing, categorizing, budgeting, forecasting, and goal tracking

---

## Installation

```bash
git clone https://github.com/jessiegibson/budgeting-app.git
cd budgeting-app
pip install -r requirements.txt
```

If using the web UI:
```bash
pip install -r requirements-ui.txt
```

---

## CLI Usage

```bash
python src/app.py [OPTIONS]
```

### Common Options

- `--full` : Full import (bypasses incremental checks)
- `--interactive` : Prompt user for column/source mapping
- `--import-pdf` : Import PDF files from `data/pdf/` or `--pdf-dir`
- `--import-qfx` : Import QFX files from `data/qfx/` or `--qfx-dir`
- `--summary` : Show transaction summary
- `--classify` : Classify transactions interactively
- `--train-model` : Train ML model for selected classification
- `--predict` : Predict categories for unclassified transactions
- `--forecast` : Generate expense forecast
- `--tax-report` : Show tax depreciation and Section 179 deduction summary

For full CLI options and modes, run:
```bash
python src/app.py --help
```

---

## Web Interface

Start the web server:
```bash
python -m src.ui
```
Visit: http://localhost:5000

### Web Features

- Dashboard: Key spending, income, and trends
- Transactions: Browse and categorize
- Budgets: Create monthly/annual budgets
- Forecast: Predict future cash flow
- Goals: Track savings and debt repayment
- Tax Deductions: View Section 179 and depreciation reports

---

## File Structure

```
budgeting-app/
├── data/              # Input data files (CSV/PDF/QFX)
│   ├── *.csv
│   └── pdf/
├── db/                # SQLite DB
│   └── transactions.db
├── models/            # ML model output
│   └── *.joblib
├── src/
│   ├── app.py         # CLI entry point
│   ├── __main__.py    # Alternate entry
│   ├── data_ingestion.py
│   ├── qfx_importer.py
│   ├── pdf_extractor.py
│   ├── ml_classifier.py
│   ├── budget_forecast.py
│   ├── budget_cashflow.py
│   ├── tax_management.py
│   ├── tax_section_179.py
│   ├── classification.py
│   └ ui.py          # Web interface
├── templates/         # HTML templates
├── static/            # CSS, JS, Images
├── logs/              # Log files
└── tests/             # Test modules
```

---

## Database Schema Highlights

**consolidated_transactions**
- `date_posted`, `description`, `amount`, `category`, `details`, `source`
- Flags: `rental_related`, `recurring`, `subscription`, `tax_deductible`, `equipment_tools`
- Metadata: `expense_category`, `recurring_group`, `recurring_freq`, `purchase_date`, `asset_value`, `depreciation_years`, `notes`

**tax_items**
- Links to transactions
- Tracks Section 179 and depreciation eligibility

**budgets**, **budget_categories**
- Stores user budgets by period, with category breakdown

**goals**, **goal_transactions**
- Track savings and debt payoff goals

---

## PDF and QFX Import Support

PDF import:
- Detects bank format
- Uses tabula or pdfplumber
- Fallback to regex parsing

QFX import:
- Parses `STMTTRN` entries
- Standardizes fields and imports to DB

---

## Machine Learning Classification

- TF-IDF + Random Forest
- Modes: `category`, `rental`, `recurring`, `subscription`, `tax`, `equipment`
- Trained models saved under `models/`
- Can batch predict with confidence thresholds
- Interactive CLI classifier for human-in-the-loop training

---

## Tax Features

- Track depreciable assets
- Section 179 deductions
- Depreciation schedule with half-year convention
- Yearly tax deduction reporting
- Visual and printable reports
---

## Budgeting & Forecasting

- Create monthly or annual budgets
- Compare actual spending
- Predict future recurring expenses
- Generate goal-based savings plans

---

## Roadmap

- 📱 Mobile-friendly interface
- ☁️ Cloud sync
- 📤 Document upload/archive
- 👥 Multi-user support

---

## License

MIT License



