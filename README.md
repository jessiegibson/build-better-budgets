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
- [NEW] Add receipt photo uploads:
  - Parse and extract line items using OCR (Tesseract)
  - Match receipt totals to transactions
  - Build inventory from SKU/description/amount data
  - Supports classification per line item
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

The application provides two command-line interfaces:

### Main Application

```bash
python src/app.py [OPTIONS]
```

### Data Ingestion Tool

For importing transactions from various sources, use the dedicated ingestion tool:

```bash
python src/ingest.py [OPTIONS]
```

#### Ingestion Options

- `--csv-dir PATH` : Directory containing CSV files to import
- `--pdf-dir PATH` : Directory containing PDF files to import
- `--qfx-dir PATH` : Directory containing QFX (Quicken) files to import
- `--full` : Full import (bypasses incremental checks)
- `--interactive` : Interactive mode for source detection
- `--summary` : Show transaction summary after import
- `--history` : Show import history

Example usage:
```bash
# Import all data types from standard locations
python src/ingest.py --csv-dir=data/csv --pdf-dir=data/pdf --qfx-dir=data/qfx

# Import only CSV files and show transaction summary
python src/ingest.py --csv-dir=data/csv --summary

# Force full import of QFX files and show history
python src/ingest.py --qfx-dir=data/qfx --full --history
```

### Main Application Options

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
│   ├── csv/ # CSV files for transactions
│   └── pdf/ # PDF files for transactions
│   └── receipts/ # receipts to be processed
│   └── qfx/ # QFX files for transactions
│   └── trans_detail/ # Detailed transaction data example Home Depot transaction detail w/ line items
│   └── output/ # Output files for processed data
├── db/                # SQLite DB
│   └── transactions.db
├── models/            # ML model output
│   └── *.joblib
├── src/
│   ├── __main__.py    # Alternate entry
│   ├──ingestion/
│   ├────__init__.py
│   ├────data_ingestion.py
│   ├────qfx_importer.py
│   ├────pdf_extractor.py
│   ├──classification/
│   ├────__init__.py
│   ├────ml_classifier.py
│   ├──budgeting/
│   ├────__init__.py
│   ├────budget_forecast.py
│   ├────budget_cashflow.py
│   ├──tax/
│   ├────__init__.py
│   ├────tax_management.py
│   ├────tax_section_179.py
│   ├──cli/
│   ├────__init__.py
│   ├────app.py         # CLI entry point
│   ├────classification.py
│   ├──static/ # CSS, JS, Images
│   ├────css/
│   ├─────style.css
│   ├────img/
│   ├────js/
│   ├─────app.js
│   ├──templates/
│   ├────analyze.htm
│   ├────base.htm
│   ├────budgets.htm
│   ├────categorize_processing.htm
│   ├────categorize.htm
│   ├────forecast.htm
│   ├────goals.htm
│   ├────index.htm
│   ├────new_budget.htm
│   ├────new_goal.htm
│   ├────tax_depreciation.htm
│   ├────tax_item_edit.htm
│   ├────tax_report.htm
│   ├────transaction_detail.htm
│   ├────transactions.htm
│   ├──utilities/
│   ├────__init__.py
│   ├────utilities.py
│   └ ui.py          # Web interface
├── logs/              # Log files
└── tests/             # Test modules
```

---

## Database Schema Highlights

**consolidated_transactions**
- `date_posted`, `description`, `amount`, `category`, `details`, `source`
- Flags: `rental_related`, `recurring`, `subscription`, `tax_deductible`, `equipment_tools`, `receipt_matched`
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
- Modes: `category`, `rental`, `recurring`, `subscriptions`, `tax`, `equipment`, `sales_tax`
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
- 📤 Document upload/archive
