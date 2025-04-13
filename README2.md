# Budgeting App

A Python application for importing, consolidating, and analyzing personal financial transactions from multiple sources.

First and for most this application ingests and normalizes the schema for banking transactions. 


## Features

- Import transactions from multiple financial sources (CSV files and PDF statements/receipts)
- Automatically detect and map transaction sources (Chase, Discover, Amex, Home Depot, etc.)
- Extract transaction data from PDF bank statements and receipts
- Standardize column names across different data sources
- Incremental importing to avoid duplicating transactions
- Logging of import history
- Consolidate transactions into a unified database format
- Interactive classification of transactions
- Track rental property expenses and categorization
- Track Section 179 deductions and depreciation for business equipment
- Summary reporting of transaction data

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/jessiegibson/budgeting-app.git
   cd budgeting-app
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Ensure you have transaction CSV files in the `data/` directory

## Usage

The application provides a command-line interface with the following options:

```
python src/app.py [options]
```

### Command Line Options

- `--full`: Perform a full import (override incremental)
- `--interactive`: Interactive mode for source naming and column mapping
- `--history`: Show import history
- `--consolidate`: Consolidate transactions from all sources
- `--summary`: Show transaction summary

**PDF Import Options:**
- `--import-pdf`: Import transactions from PDF files
- `--pdf-dir PATH`: Directory containing PDF files to import (defaults to data/pdf)

**Classification Options:**
- `--classify`: Run interactive classification
- `--mode`: Classification mode (all, rental, recurring, subscription, tax, equipment)
- `--sample-size SAMPLE_SIZE`: Number of transactions to classify per batch (default: 5)
- `--detect-recurring`: Automatically detect recurring transactions

**Machine Learning Options:**
- `--train-model`: Train a machine learning model for rental classification
- `--predict`: Use ML model to predict rental classifications
- `--predict-limit LIMIT`: Number of transactions to predict (default: 100)

### Common Workflows

#### Initial Setup

```bash
# Full import and consolidation of all data (automatic mode)
python src/app.py --full --consolidate

# Full import in interactive mode (manually name sources and map columns)
python src/app.py --full --interactive --consolidate

# Import PDFs and consolidate
python src/app.py --import-pdf --consolidate
```

#### Regular Updates

```bash
# Import only new transactions (incremental) and consolidate
python src/app.py --consolidate

# Import new transactions in interactive mode
python src/app.py --interactive --consolidate

# Import PDFs from a specific directory
python src/app.py --import-pdf --pdf-dir /path/to/pdf/files

# Import both CSVs and PDFs
python src/app.py --import-pdf --consolidate

# View import history
python src/app.py --history

# View transaction summary
python src/app.py --summary
```

#### Transaction Classification

```bash
# Automatically detect recurring transactions
python src/app.py --detect-recurring

# Classify 5 transactions at a time (all classification types)
python src/app.py --classify

# Focus on classifying just recurring transactions
python src/app.py --classify --mode recurring

# Focus on classifying just rental expenses
python src/app.py --classify --mode rental

# Focus on classifying depreciable equipment and tools
python src/app.py --classify --mode equipment

# Focus on classifying subscription services
python src/app.py --classify --mode subscription

# Focus on classifying tax-deductible expenses
python src/app.py --classify --mode tax

# Classify 10 transactions at a time
python src/app.py --classify --sample-size 10
```

#### Machine Learning Classification

```bash
# Train a machine learning model after manually classifying some transactions
python src/app.py --train-model

# Use the trained model to predict classifications for unclassified transactions
python src/app.py --predict

# Predict classifications for up to 500 transactions
python src/app.py --predict --predict-limit 500
```

## Data Structure

The application supports multiple financial data sources. Transactions are imported into source-specific tables and then consolidated into a unified format for analysis.

### Supported Data Sources

- Chase Bank
- Discover Card
- American Express (Platinum & Rose & Delta)
- Home Depot
- Wealthfront
- Capital One
- Apple Card
- SoFi
- Ally Bank

### Database Schema

The consolidated transactions table contains the following fields:

- `id`: Unique identifier
- `date_posted`: Date of the transaction
- `description`: Transaction description
- `amount`: Transaction amount
- `category`: Transaction category (if provided by the source)
- `details`: Additional transaction details
- `source`: Source of the transaction (e.g., 'chase', 'discover')

**Classification Fields:**
- `rental_related`: Flag indicating if the transaction is rental property related
- `expense_category`: User-defined expense category
- `maintenance_upgrade`: Indicates if a rental expense is maintenance or an upgrade
- `recurring`: Flag indicating if this is a recurring transaction
- `recurring_group`: Group ID for recurring transactions (e.g., same bill from different months)
- `recurring_freq`: Frequency of recurrence (MONTHLY, WEEKLY, QUARTERLY, YEARLY)
- `subscription`: Flag indicating if this is a subscription service
- `tax_deductible`: Flag indicating if this expense is tax deductible
- `equipment_tools`: Flag indicating if this is depreciable equipment or tool
- `purchase_date`: Date when the equipment/tool was purchased (for depreciation tracking)
- `asset_value`: The value of the asset (may differ from transaction amount)
- `depreciation_years`: Number of years over which to depreciate the equipment/tool
- `notes`: User notes about the transaction

**Tax-Related Tables:**

`tax_items` table:
- `id`: Unique identifier
- `description`: Description of the asset
- `purchase_date`: Date the asset was placed in service
- `amount`: Purchase amount
- `business_use_percentage`: Percentage of business use (1-100%)
- `depreciation_years`: Number of years for depreciation
- `use_section_179`: Whether Section 179 deduction is elected
- `transaction_id`: Related transaction ID (optional)
- `tax_year`: Year of purchase
- `deduction_taken`: Amount of deduction already taken
- `notes`: Additional notes

`tax_depreciation_history` table:
- `id`: Unique identifier
- `tax_item_id`: Related tax item
- `tax_year`: Tax year
- `depreciation_amount`: Regular depreciation amount for this year
- `section_179_amount`: Section 179 deduction amount for this year

`tax_settings` table:
- `id`: Unique identifier
- `setting_name`: Name of the setting (e.g., section_179_limit_2023)
- `setting_value`: Value of the setting
- `updated_at`: Last update timestamp

## File Structure
src/
├── cli/                  
│   └── main.py               # Entry point for CLI
│   └── classification_cli.py # All CLI-based interaction
│   └── budgeting_cli.py      # Budget creation and reporting from CLI
├── ingestion/
│   ├── data_ingestion.py     # CSV/QFX/PDF ingestion and mapping
│   ├── qfx_importer.py
│   ├── pdf_extractor.py
├── classification/
│   ├── ml_classifier.py      # Model training & inference
│   └── category_suggester.py # Prediction utilities
├── budgeting/
│   ├── budget_forecast.py
│   ├── budget_cashflow.py
├── tax/
│   ├── tax_management.py
│   └── section_179.py
├── reporting/
│   ├── summary.py            # Show import summaries, stats
│   └── charts.py             # For plotly or visual summaries
├── utils/
│   ├── column_mapper.py      # rename_columns, date mapping
│   └── common.py
├── ui/
   └── flask_ui.py



## Virtual Environments 
Currently, we are using the 'budgeting_app_v1' for the most current virtual environment using python 3.12.

## PDF Transaction Import

The application includes sophisticated PDF parsing capabilities to extract transaction data from various PDF formats:

### Supported PDF Types
- Bank statements (Chase, Amex, Discover, etc.)
- Credit card statements
- Receipts and invoices
- Purchase history reports

### PDF Import Process
1. **Format Detection**: The system analyzes PDF content to detect the source/format
2. **Table Extraction**: Structured tables are extracted using multiple techniques
3. **Data Mapping**: Column names are mapped to standardized fields
4. **Date Standardization**: Various date formats are converted to YYYY-MM-DD
5. **CSV Conversion**: Extracted data is converted to CSV for database import

### Usage
1. Place PDF files in the `data/pdf/` directory (or specify directory with `--pdf-dir`)
2. Run `python src/app.py --import-pdf`
3. The system will automatically detect formats, extract data, and import to database
4. Use `--interactive` flag to manually map fields if needed

The PDF import uses a multi-stage fallback approach:
1. First tries Java-based table extraction (most accurate for structured tables)
2. Falls back to PDF plumber for documents with non-standard table formats
3. Uses text-based extraction with pattern matching as last resort
4. Extracts line items from receipts when possible

## Machine Learning Classification

The application includes machine learning capabilities to automatically classify transactions as rental-related or not:

1. **Training Data**: Manually classify a subset of transactions using the `--classify` option.
2. **Model Training**: Train a machine learning model using the `--train-model` option.
3. **Prediction**: Apply the model to unclassified transactions using the `--predict` option.

The model uses:
- TF-IDF vectorization of transaction descriptions
- Random Forest classifier with balanced class weights
- Confidence thresholds for applying predictions
- Transaction clustering. 

Models are saved in the `models/` directory with timestamped filenames.

## Web Interface

The application now includes a web interface for easier interaction with your financial data:

### Web Features
- **Dashboard**: Overview of financial situation with key metrics and charts
- **Transactions**: Browse, search, filter, and categorize all transactions
- **Budgets**: Create and manage category-based budgets
- **Goals**: Set up and track financial goals
- **Forecast**: View cash flow projections based on recurring transactions
- **Smart Categorization**: Bulk categorization of transactions with ML assistance
- **Analysis**: Spending patterns and insights with visualizations
- **Tax Deductions**: Track and report business equipment purchases with Section 179 deductions and depreciation schedules

### Running the Web Interface

Install the UI dependencies:
```
pip install -r requirements-ui.txt
```

Run the web interface with:
```
python -m src.ui
```

Then open your browser to http://localhost:5000

## Tax Deduction and Depreciation Features

The application includes comprehensive tools for tracking business equipment purchases, calculating Section 179 deductions, and managing asset depreciation:

### Section 179 Deduction Features
- Track business equipment and property eligible for Section 179 deduction
- Automatically calculate deduction limits and carry-over amounts
- Adjust business use percentage for partially business-used assets
- Link tax items to existing transactions in the system
- Generate detailed tax reports for any tax year

### Depreciation Features
- Support for multiple depreciation periods (5, 7, 15, 27.5, and 39 years)
- Automatic straight-line depreciation calculation with half-year convention
- Visual depreciation schedule showing deduction amounts by year
- Projected tax deductions for future tax planning
- Comprehensive reporting for tax preparation

### Tax Reports
- Generate itemized tax reports showing all Section 179 and depreciable assets
- Print-friendly reports that can be used for tax filing
- CSV export functionality for integration with tax software
- Reference information for filling out Form 4562

### Usage

Navigate to the Tax Deductions section in the web interface to:
1. Add equipment purchases by selecting from existing transactions or entering manually
2. Choose between Section 179 immediate expensing or regular depreciation
3. Generate tax reports for the current or previous tax years
4. View depreciation schedules and projected tax deductions

## Future Improvements

- Enhanced ML features using transaction amounts and categories
- Mobile-friendly interface
- Financial document upload and storage
- Multiple user accounts

## License

This project is licensed under the MIT License - see the LICENSE file for details
# Budgeting App

A comprehensive Python application for importing, consolidating, and analyzing personal financial transactions from multiple sources. This application ingests CSV, PDF, and QFX files to provide advanced budgeting, forecasting, goal tracking, and tax optimization capabilities.


## Features

- Import transactions from multiple financial sources (CSV files, PDF statements/receipts and QFX quicken exports.) The transaction files should be uploaded into the application. 
- Automatically detect and map transaction sources (Chase, Discover, Amex, Home Depot, etc.)
- Extract transaction data from PDF bank statements and receipts
- Standardize column names across different data sources
- Incremental importing to avoid duplicating transactions
- Logging of import history
- Consolidate transactions into a unified database format using either DuckDb or sqlite3. 
- Machine Learning classification algorithm to classify transactions with an interactive classification for the user to train the model.
- Create an annual budget using machine learning to optimize savings or paying off bills.
- Goals to help track savings, debt reductions for specific purposes.
- Track rental property expenses and categorization based on if the expenses are maintenance on the property or upgrades to the property. 
- Track Section 179 deductions and depreciation for business equipment
- Summary reporting of transaction data
- Tax preperation, assist in preparing itemized deductions.
- Web interface that allows the user to see recurring transactions, build monthly budgets, forecast expenses, as well as understand cashflow. 

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/jessiegibson/budgeting-app.git
   cd budgeting-app
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Ensure you have transaction CSV files in the `data/` directory

## Usage

The application provides both a CLI and a web app UI. The application provides a command-line interface with the following options:

```
python src/app.py [options]
```

### Command Line Options

- `--full`: Perform a full import (override incremental)
- `--interactive`: Interactive mode for source naming and column mapping
- `--history`: Show import history
- `--consolidate`: Consolidate transactions from all sources
- `--summary`: Show transaction summary

**PDF Import Options:**
- `--import-pdf`: Import transactions from PDF files
- `--pdf-dir PATH`: Directory containing PDF files to import (defaults to data/pdf)

**Classification Options:**
- `--classify`: Run interactive classification
- `--mode`: Classification mode (all, rental, recurring, subscription, tax, equipment)
- `--sample-size SAMPLE_SIZE`: Number of transactions to classify per batch (default: 5)
- `--detect-recurring`: Automatically detect recurring transactions

**Machine Learning Options:**
- `--train-model`: Train a machine learning model for rental classification
- `--predict`: Use ML model to predict rental classifications
- `--predict-limit LIMIT`: Number of transactions to predict (default: 100)

### Common Workflows

#### Initial Setup

```bash
# Full import and consolidation of all data (automatic mode)
python src/app.py --full --consolidate

# Full import in interactive mode (manually name sources and map columns)
python src/app.py --full --interactive --consolidate

# Import PDFs and consolidate
python src/app.py --import-pdf --consolidate
```

#### Regular Updates

```bash
# Import only new transactions (incremental) and consolidate
python src/app.py --consolidate

# Import new transactions in interactive mode
python src/app.py --interactive --consolidate

# Import PDFs from a specific directory
python src/app.py --import-pdf --pdf-dir /path/to/pdf/files

# Import both CSVs and PDFs
python src/app.py --import-pdf --consolidate

# View import history
python src/app.py --history

# View transaction summary
python src/app.py --summary
```

#### Transaction Classification

```bash
# Automatically detect recurring transactions
python src/app.py --detect-recurring

# Classify 5 transactions at a time (all classification types)
python src/app.py --classify

# Focus on classifying just recurring transactions
python src/app.py --classify --mode recurring

# Focus on classifying just rental expenses
python src/app.py --classify --mode rental

# Focus on classifying depreciable equipment and tools
python src/app.py --classify --mode equipment

# Focus on classifying subscription services
python src/app.py --classify --mode subscription

# Focus on classifying tax-deductible expenses
python src/app.py --classify --mode tax

# Classify 10 transactions at a time
python src/app.py --classify --sample-size 10
```

#### Machine Learning Classification

```bash
# Train a machine learning model after manually classifying some transactions
python src/app.py --train-model

# Use the trained model to predict classifications for unclassified transactions
python src/app.py --predict

# Predict classifications for up to 500 transactions
python src/app.py --predict --predict-limit 500
```

## Data Structure

The application supports multiple financial data sources. Transactions are imported into source-specific tables and then consolidated into a unified format for analysis.

### Supported Data Sources

- Chase Bank
- Discover Card
- American Express (Platinum & Rose & Delta)
- Home Depot
- Wealthfront
- Capital One
- Apple Card
- SoFi
- Ally Bank
- PennyMac
- PNC Bank
- Bank of Ameica


### Database Schema

The consolidated transactions table contains the following fields:

- `id`: Unique identifier
- `date_posted`: Date of the transaction
- `description`: Transaction description
- `amount`: Transaction amount
- `category`: Transaction category (if provided by the source)
- `details`: Additional transaction details
- `source`: Source of the transaction (e.g., 'chase', 'discover')

**Classification Fields:**
- `rental_related`: Flag indicating if the transaction is rental property related
- `expense_category`: User-defined expense category
- `maintenance_upgrade`: Indicates if a rental expense is maintenance or an upgrade
- `recurring`: Flag indicating if this is a recurring transaction
- `recurring_group`: Group ID for recurring transactions (e.g., same bill from different months)
- `recurring_freq`: Frequency of recurrence (MONTHLY, WEEKLY, QUARTERLY, YEARLY)
- `subscription`: Flag indicating if this is a subscription service
- `tax_deductible`: Flag indicating if this expense is tax deductible
- `equipment_tools`: Flag indicating if this is depreciable equipment or tool
- `purchase_date`: Date when the equipment/tool was purchased (for depreciation tracking)
- `asset_value`: The value of the asset (may differ from transaction amount)
- `depreciation_years`: Number of years over which to depreciate the equipment/tool
- `notes`: User notes about the transaction

**Tax-Related Tables:**

`tax_items` table:
- `id`: Unique identifier
- `description`: Description of the asset
- `purchase_date`: Date the asset was placed in service
- `amount`: Purchase amount
- `business_use_percentage`: Percentage of business use (1-100%)
- `depreciation_years`: Number of years for depreciation
- `use_section_179`: Whether Section 179 deduction is elected
- `transaction_id`: Related transaction ID (optional)
- `tax_year`: Year of purchase
- `deduction_taken`: Amount of deduction already taken
- `notes`: Additional notes

`tax_depreciation_history` table:
- `id`: Unique identifier
- `tax_item_id`: Related tax item
- `tax_year`: Tax year
- `depreciation_amount`: Regular depreciation amount for this year
- `section_179_amount`: Section 179 deduction amount for this year

`tax_settings` table:
- `id`: Unique identifier
- `setting_name`: Name of the setting (e.g., section_179_limit_2023)
- `setting_value`: Value of the setting
- `updated_at`: Last update timestamp

## File Structure

budgeting-app/
├── README.md              # Documentation for your application
├── data/                  # Placeholder for raw data files
│   ├── *.csv              # Transaction data CSV files
│   └── pdf/               # PDF statements and receipts for import
├── db/                    # Database files
│   └── transactions.db    # SQLite database file
├── models/                # Machine learning models
│   ├── category_classifier_*.joblib     # Transaction category classifiers
│   ├── rental_classifier_*.joblib       # Rental property classifiers
│   └── valid_categories.txt             # List of valid categories for ML
├── src/                   # Source code
│   ├── app.py             # Main application file
│   ├── ui.py              # Web interface
│   ├── __main__.py        # Entry point
│   ├── static/            # Static assets for web interface
│   │   ├── css/           # CSS stylesheets
│   │   ├── js/            # JavaScript files
│   │   └── img/           # Images
│   └── templates/         # HTML templates
│       ├── base.html      # Base template
│       ├── index.html     # Dashboard
│       ├── transactions.html # Transactions list
│       ├── analyze.html   # Analytics
│       ├── tax_depreciation.html  # Tax deduction tracking
│       └── tax_report.html      # Tax reports
└── tests/                 # Test cases

## Virtual Environments 
Currently, we are using the 'budgeting_app_v1' for the most current virtual environment using python 3.12.

## PDF Transaction Import

The application includes sophisticated PDF parsing capabilities to extract transaction data from various PDF formats:

### Supported PDF Types
- Bank statements (Chase, Amex, Discover, etc.)
- Credit card statements
- Receipts and invoices
- Purchase history reports

### PDF Import Process
1. **Format Detection**: The system analyzes PDF content to detect the source/format
2. **Table Extraction**: Structured tables are extracted using multiple techniques
3. **Data Mapping**: Column names are mapped to standardized fields
4. **Date Standardization**: Various date formats are converted to YYYY-MM-DD
5. **CSV Conversion**: Extracted data is converted to CSV for database import

### Usage
1. Place PDF files in the `data/pdf/` directory (or specify directory with `--pdf-dir`)
2. Run `python src/app.py --import-pdf`
3. The system will automatically detect formats, extract data, and import to database
4. Use `--interactive` flag to manually map fields if needed

The PDF import uses a multi-stage fallback approach:
1. First tries Java-based table extraction (most accurate for structured tables)
2. Falls back to PDF plumber for documents with non-standard table formats
3. Uses text-based extraction with pattern matching as last resort
4. Extracts line items from receipts when possible

## Machine Learning Classification

The application includes machine learning capabilities to automatically classify transactions as rental-related or not:

1. **Training Data**: Manually classify a subset of transactions using the `--classify` option.
2. **Model Training**: Train a machine learning model using the `--train-model` option.
3. **Prediction**: Apply the model to unclassified transactions using the `--predict` option.

The model uses:
- TF-IDF vectorization of transaction descriptions
- Random Forest classifier with balanced class weights
- Confidence thresholds for applying predictions
- Transaction clustering. 

Models are saved in the `models/` directory with timestamped filenames.

## Web Interface

The application now includes a web interface for easier interaction with your financial data:

### Web Features
- **Dashboard**: Overview of financial situation with key metrics and charts
- **Transactions**: Browse, search, filter, and categorize all transactions
- **Budgets**: Create and manage category-based budgets
- **Goals**: Set up and track financial goals
- **Forecast**: View cash flow projections based on recurring transactions
- **Smart Categorization**: Bulk categorization of transactions with ML assistance
- **Analysis**: Spending patterns and insights with visualizations
- **Tax Deductions**: Track and report business equipment purchases with Section 179 deductions and depreciation schedules

### Running the Web Interface

Install the UI dependencies:
```
pip install -r requirements-ui.txt
```

Run the web interface with:
```
python -m src.ui
```

Then open your browser to http://localhost:5000

## Tax Deduction and Depreciation Features

The application includes comprehensive tools for tracking business equipment purchases, calculating Section 179 deductions, and managing asset depreciation:

### Section 179 Deduction Features
- Track business equipment and property eligible for Section 179 deduction
- Automatically calculate deduction limits and carry-over amounts
- Adjust business use percentage for partially business-used assets
- Link tax items to existing transactions in the system
- Generate detailed tax reports for any tax year

### Depreciation Features
- Support for multiple depreciation periods (5, 7, 15, 27.5, and 39 years)
- Automatic straight-line depreciation calculation with half-year convention
- Visual depreciation schedule showing deduction amounts by year
- Projected tax deductions for future tax planning
- Comprehensive reporting for tax preparation

### Tax Reports
- Generate itemized tax reports showing all Section 179 and depreciable assets
- Print-friendly reports that can be used for tax filing
- CSV export functionality for integration with tax software
- Reference information for filling out Form 4562

### Usage

Navigate to the Tax Deductions section in the web interface to:
1. Add equipment purchases by selecting from existing transactions or entering manually
2. Choose between Section 179 immediate expensing or regular depreciation
3. Generate tax reports for the current or previous tax years
4. View depreciation schedules and projected tax deductions

## Future Improvements

- Enhanced ML features using transaction amounts and categories
- Mobile-friendly interface
- Financial document upload and storage
- Multiple user accounts

## License

This project is licensed under the MIT License - see the LICENSE file for details

