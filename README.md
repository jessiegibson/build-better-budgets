# Budgeting App

A Python application for importing, consolidating, and analyzing personal financial transactions from multiple sources.

## Features

- Import transactions from multiple financial sources (CSV files)
- Automatically detect and map transaction sources (Chase, Discover, Amex, Home Depot, etc.)
- Standardize column names across different data sources
- Incremental importing to avoid duplicating transactions
- Logging of import history
- Consolidate transactions into a unified database format
- Interactive classification of transactions
- Track rental property expenses and categorization
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
```

#### Regular Updates

```bash
# Import only new transactions (incremental) and consolidate
python src/app.py --consolidate

# Import new transactions in interactive mode
python src/app.py --interactive --consolidate

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
- American Express (Platinum & Rose)
- Home Depot

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

## File Structure

budgeting-app/
├── README.md              # Documentation for your application
├── data/                  # Placeholder for raw CSVs or sample data
│   └── *.csv              # Transaction data files
├── db/                    # Database files
│   └── transactions.db    # SQLite database file
├── src/                   # Source code
│   ├── app.py             # Main application file
│   └── __main__.py        # Entry point
└── tests/                 # Test cases

## Virtual Environments 
Currently, we are using the 'budgeting_app_v1' for the most current virtual environment using python 3.12.

## Machine Learning Classification

The application includes machine learning capabilities to automatically classify transactions as rental-related or not:

1. **Training Data**: Manually classify a subset of transactions using the `--classify` option.
2. **Model Training**: Train a machine learning model using the `--train-model` option.
3. **Prediction**: Apply the model to unclassified transactions using the `--predict` option.

The model uses:
- TF-IDF vectorization of transaction descriptions
- Random Forest classifier with balanced class weights
- Confidence thresholds for applying predictions

Models are saved in the `models/` directory with timestamped filenames.

## Future Improvements

- Web interface for transaction viewing and classification
- Data visualization and reporting
- Budget tracking and planning
- Tax report generation for rental properties
- Enhanced ML features using transaction amounts and categories
- Monthly and yearly spending reports

## License

This project is licensed under the MIT License - see the LICENSE file for details