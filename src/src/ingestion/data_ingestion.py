"""
Data Ingestion Module

Provides functionality for importing, standardizing, and consolidating 
financial transaction data from various sources.
"""

import os
import glob
import pandas as pd
import sqlite3
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Union

# Import local modules
from src.pdf_extractor import extract_transactions_from_pdf, pdf_to_csv, process_pdf_directory
from src.qfx_importer import parse_qfx_file, qfx_to_csv, process_qfx_directory

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database connection
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db', 'transactions.db')

def get_db_connection() -> sqlite3.Connection:
    """Create a database connection with row factory set for dictionary access."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database() -> None:
    """Initialize the database with necessary tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create consolidated transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS consolidated_transactions (
            id INTEGER PRIMARY KEY,
            date_posted TEXT,
            description TEXT,
            amount REAL,
            category TEXT,
            details TEXT,
            source TEXT,
            rental_related INTEGER DEFAULT 0,
            expense_category TEXT,
            maintenance_upgrade TEXT,
            recurring INTEGER DEFAULT 0,
            recurring_group TEXT,
            recurring_freq TEXT,
            subscription INTEGER DEFAULT 0,
            tax_deductible INTEGER DEFAULT 0,
            equipment_tools INTEGER DEFAULT 0,
            purchase_date TEXT,
            asset_value REAL,
            depreciation_years INTEGER,
            notes TEXT
        )
    ''')
    
    # Create import_log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS import_log (
            id INTEGER PRIMARY KEY,
            source TEXT,
            filename TEXT,
            import_date TEXT,
            record_count INTEGER,
            md5_hash TEXT
        )
    ''')
    
    # Create budgets table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY,
            name TEXT,
            start_date TEXT,
            end_date TEXT,
            total_amount REAL,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create budget_categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS budget_categories (
            id INTEGER PRIMARY KEY,
            budget_id INTEGER,
            category TEXT,
            amount REAL,
            FOREIGN KEY (budget_id) REFERENCES budgets(id)
        )
    ''')
    
    # Create goals table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY,
            name TEXT,
            target_amount REAL,
            current_amount REAL DEFAULT 0,
            start_date TEXT,
            target_date TEXT,
            category TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create goal_transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS goal_transactions (
            id INTEGER PRIMARY KEY,
            goal_id INTEGER,
            amount REAL,
            date TEXT,
            notes TEXT,
            FOREIGN KEY (goal_id) REFERENCES goals(id)
        )
    ''')
    
    # Create recurring_forecasts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recurring_forecasts (
            id INTEGER PRIMARY KEY,
            description TEXT,
            amount REAL,
            frequency TEXT,
            next_date TEXT,
            category TEXT,
            source TEXT,
            recurring_group TEXT,
            notes TEXT
        )
    ''')
    
    # Create tax_items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tax_items (
            id INTEGER PRIMARY KEY,
            description TEXT,
            purchase_date TEXT,
            amount REAL,
            business_use_percentage REAL DEFAULT 100.0,
            depreciation_years INTEGER,
            use_section_179 INTEGER DEFAULT 0,
            transaction_id INTEGER,
            tax_year INTEGER,
            deduction_taken REAL DEFAULT 0.0,
            notes TEXT,
            FOREIGN KEY (transaction_id) REFERENCES consolidated_transactions(id)
        )
    ''')
    
    # Create tax_depreciation_history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tax_depreciation_history (
            id INTEGER PRIMARY KEY,
            tax_item_id INTEGER,
            tax_year INTEGER,
            depreciation_amount REAL,
            section_179_amount REAL,
            FOREIGN KEY (tax_item_id) REFERENCES tax_items(id)
        )
    ''')
    
    # Create tax_settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tax_settings (
            id INTEGER PRIMARY KEY,
            setting_name TEXT UNIQUE,
            setting_value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insert default Section 179 limits if not present
    cursor.execute("SELECT COUNT(*) FROM tax_settings WHERE setting_name LIKE 'section_179_limit_%'")
    if cursor.fetchone()[0] == 0:
        # Insert default Section 179 limits for recent years
        limits = [
            ('section_179_limit_2023', '1160000'),
            ('section_179_limit_2024', '1220000'),
            ('section_179_limit_2025', '1250000'),  # Projected
        ]
        cursor.executemany("INSERT INTO tax_settings (setting_name, setting_value) VALUES (?, ?)", limits)
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def detect_csv_source(filepath: str, content_preview: pd.DataFrame) -> str:
    """
    Detect the source of a CSV file based on filename and content.
    
    Args:
        filepath: Path to the CSV file
        content_preview: Preview of the CSV content as DataFrame
        
    Returns:
        Detected source name (e.g., 'chase', 'discover')
    """
    filename = os.path.basename(filepath).lower()
    
    # Check filename patterns
    if 'chase' in filename:
        return 'chase'
    elif 'discover' in filename:
        return 'discover'
    elif 'amex' in filename or 'american express' in filename:
        return 'amex'
    elif 'homedepot' in filename or 'home depot' in filename or 'thd' in filename:
        return 'home_depot'
    elif 'wealthfront' in filename:
        return 'wealthfront'
    elif 'capital one' in filename or 'capitalone' in filename:
        return 'capital_one'
    elif 'apple card' in filename or 'applecard' in filename:
        return 'apple_card'
    elif 'sofi' in filename:
        return 'sofi'
    elif 'ally' in filename:
        return 'ally'
    elif 'pennymac' in filename:
        return 'pennymac'
    elif 'pnc' in filename:
        return 'pnc'
    elif 'bank of america' in filename or 'bankofamerica' in filename or 'bofa' in filename:
        return 'bofa'
    
    # If not found by filename, check column names
    columns = [col.lower() if isinstance(col, str) else col for col in content_preview.columns]
    
    # Common column patterns by source
    patterns = {
        'chase': ['transaction date', 'post date', 'description', 'amount', 'type'],
        'discover': ['trans. date', 'post date', 'description', 'amount', 'category'],
        'amex': ['date', 'description', 'amount', 'extended details', 'appearing as'],
        'home_depot': ['order date', 'order number', 'product description', 'item total'],
        'capital_one': ['transaction date', 'posted date', 'card no.', 'description', 'debit', 'credit'],
        'apple_card': ['transaction date', 'description', 'merchant', 'category', 'type', 'amount'],
        'ally': ['date', 'time', 'amount', 'type', 'description'],
        'bofa': ['date', 'description', 'amount', 'running balance']
    }
    
    for source, pattern in patterns.items():
        matches = sum(1 for col in pattern if any(pcol.lower() == col.lower() if isinstance(pcol, str) else False 
                                              for pcol in columns))
        if matches >= len(pattern) // 2:  # If at least half the columns match
            return source
    
    # If still not detected, return generic
    return 'generic'

def map_columns(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """
    Map source-specific columns to standardized column names.
    
    Args:
        df: DataFrame with source-specific columns
        source: Detected source name
        
    Returns:
        DataFrame with standardized columns
    """
    # Column mapping for each source
    mappings = {
        'chase': {
            'date': ['Transaction Date', 'Post Date'],
            'description': ['Description'],
            'amount': ['Amount'],
            'category': ['Category'],
            'details': ['Type']
        },
        'discover': {
            'date': ['Trans. Date', 'Post Date'],
            'description': ['Description'],
            'amount': ['Amount'],
            'category': ['Category'],
            'details': ['']
        },
        'amex': {
            'date': ['Date'],
            'description': ['Description'],
            'amount': ['Amount'],
            'category': ['Category'],
            'details': ['Extended Details', 'Appearing As']
        },
        'home_depot': {
            'date': ['Order Date'],
            'description': ['Product Description'],
            'amount': ['Item Total'],
            'category': [''],
            'details': ['Order Number']
        },
        'capital_one': {
            'date': ['Transaction Date', 'Posted Date'],
            'description': ['Description'],
            'amount': ['Debit', 'Credit'],  # Need special handling
            'category': [''],
            'details': ['Card No.']
        },
        'apple_card': {
            'date': ['Transaction Date'],
            'description': ['Description', 'Merchant'],
            'amount': ['Amount'],
            'category': ['Category'],
            'details': ['Type']
        },
        'bofa': {
            'date': ['Date'],
            'description': ['Description'],
            'amount': ['Amount'],
            'category': [''],
            'details': ['Running Balance']
        },
        'ally': {
            'date': ['Date'],
            'description': ['Description'],
            'amount': ['Amount'],
            'category': [''],
            'details': ['Type']
        },
        'pennymac': {
            'date': ['Date'],
            'description': ['Description'],
            'amount': ['Amount'],
            'category': [''],
            'details': ['']
        },
        'pnc': {
            'date': ['Date'],
            'description': ['Description'],
            'amount': ['Amount'],
            'category': [''],
            'details': ['']
        },
        'sofi': {
            'date': ['Date'],
            'description': ['Description'],
            'amount': ['Amount'],
            'category': [''],
            'details': ['']
        },
        'wealthfront': {
            'date': ['Date'],
            'description': ['Description'],
            'amount': ['Amount'],
            'category': [''],
            'details': ['']
        }
    }
    
    # Handle generic if not in mappings
    if source not in mappings:
        source = 'generic'
        mappings['generic'] = {
            'date': ['Date', 'Transaction Date', 'Trans Date', 'Posted Date'],
            'description': ['Description', 'Merchant', 'Payee', 'Transaction'],
            'amount': ['Amount', 'Total', 'Price', 'Cost'],
            'category': ['Category', 'Type'],
            'details': ['Details', 'Notes', 'Reference', 'Trans ID']
        }
    
    # Create new DataFrame with standardized columns
    result = pd.DataFrame()
    
    # For each standardized column, find the matching source column
    for std_col, source_cols in mappings[source].items():
        # Find first matching column in the source data
        matched = False
        for source_col in source_cols:
            if source_col and source_col in df.columns:
                result[std_col] = df[source_col]
                matched = True
                break
        
        # If no match found, add empty column
        if not matched:
            result[std_col] = ''
    
    # Special handling for Capital One credit/debit columns
    if source == 'capital_one' and 'Debit' in df.columns and 'Credit' in df.columns:
        # Combine Debit and Credit into a single Amount column
        # Debit is negative, Credit is positive
        result['amount'] = df['Debit'].fillna(0) * -1 + df['Credit'].fillna(0)
    
    # Add source column
    result['source'] = source
    
    # Clean up amount column - remove $ and , characters
    if 'amount' in result.columns:
        result['amount'] = result['amount'].astype(str).str.replace('$', '').str.replace(',', '')
        result['amount'] = pd.to_numeric(result['amount'], errors='coerce')
    
    # Standardize date format to YYYY-MM-DD
    if 'date' in result.columns:
        result['date'] = pd.to_datetime(result['date'], errors='coerce').dt.strftime('%Y-%m-%d')
    
    return result

def import_csv_file(filepath: str, interactive: bool = False, full_import: bool = False) -> Tuple[str, int]:
    """
    Import transactions from a CSV file into a source-specific table.
    
    Args:
        filepath: Path to the CSV file
        interactive: Whether to prompt user for source detection and column mapping
        full_import: Whether to perform a full import (ignore import history)
        
    Returns:
        Tuple of (source_name, record_count)
    """
    logger.info(f"Importing CSV file: {filepath}")
    
    # Read CSV file
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        logger.error(f"Error reading CSV file {filepath}: {e}")
        return None, 0
    
    if df.empty:
        logger.warning(f"Empty CSV file: {filepath}")
        return None, 0
    
    # Detect source
    source = detect_csv_source(filepath, df)
    
    # In interactive mode, prompt for source
    if interactive:
        detected = source
        source = input(f"Detected source as '{detected}'. Enter source name or press Enter to confirm: ")
        if not source:
            source = detected
    
    logger.info(f"CSV source detected as: {source}")
    
    # Map columns to standard format
    standardized_df = map_columns(df, source)
    
    # Check if we have already imported this file
    conn = get_db_connection()
    cursor = conn.cursor()
    
    filename = os.path.basename(filepath)
    cursor.execute("SELECT * FROM import_log WHERE source = ? AND filename = ?", (source, filename))
    import_record = cursor.fetchone()
    
    # If we've imported before and not doing a full import, check for new records
    if import_record and not full_import:
        last_import_date = import_record['import_date']
        logger.info(f"Previous import found for {filename} on {last_import_date}")
        
        # Only import new transactions (those with later dates)
        if 'date' in standardized_df.columns:
            standardized_df = standardized_df[standardized_df['date'] > last_import_date]
            
        if standardized_df.empty:
            logger.info(f"No new transactions to import from {filepath}")
            conn.close()
            return source, 0
    
    # Insert into consolidated_transactions directly
    record_count = 0
    for _, row in standardized_df.iterrows():
        try:
            cursor.execute('''
                INSERT INTO consolidated_transactions 
                (date_posted, description, amount, category, details, source)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                row['date'],
                row['description'],
                row['amount'],
                row['category'] if 'category' in row and pd.notna(row['category']) else '',
                row['details'] if 'details' in row and pd.notna(row['details']) else '',
                source
            ))
            record_count += 1
        except Exception as e:
            logger.error(f"Error inserting row: {e}")
    
    # Update import log
    import_date = datetime.now().strftime('%Y-%m-%d')
    if import_record:
        cursor.execute('''
            UPDATE import_log 
            SET import_date = ?, record_count = record_count + ?
            WHERE id = ?
        ''', (import_date, record_count, import_record['id']))
    else:
        cursor.execute('''
            INSERT INTO import_log (source, filename, import_date, record_count)
            VALUES (?, ?, ?, ?)
        ''', (source, filename, import_date, record_count))
    
    conn.commit()
    conn.close()
    
    logger.info(f"Imported {record_count} records from {filepath}")
    return source, record_count

def import_all_csv_files(data_dir: str, interactive: bool = False, full_import: bool = False) -> Dict[str, int]:
    """
    Import all CSV files from a directory.
    
    Args:
        data_dir: Directory containing CSV files
        interactive: Whether to prompt user for source detection and column mapping
        full_import: Whether to perform a full import (ignore import history)
        
    Returns:
        Dictionary mapping source names to record counts
    """
    result = {}
    
    # Get all CSV files
    csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
    csv_files.extend(glob.glob(os.path.join(data_dir, "*.CSV")))
    
    if not csv_files:
        logger.warning(f"No CSV files found in {data_dir}")
        return result
    
    logger.info(f"Found {len(csv_files)} CSV files in {data_dir}")
    
    for filepath in csv_files:
        try:
            source, count = import_csv_file(filepath, interactive, full_import)
            if source:
                if source in result:
                    result[source] += count
                else:
                    result[source] = count
        except Exception as e:
            logger.error(f"Error processing {filepath}: {e}")
    
    return result

def import_pdf_files(pdf_dir: str = None, interactive: bool = False, full_import: bool = False) -> Dict[str, int]:
    """
    Import transactions from PDF files.
    
    Args:
        pdf_dir: Directory containing PDF files (default: data/pdf)
        interactive: Whether to prompt user for source detection and column mapping
        full_import: Whether to perform a full import (ignore import history)
        
    Returns:
        Dictionary mapping source names to record counts
    """
    # Default PDF directory
    if pdf_dir is None:
        pdf_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'pdf')
    
    if not os.path.exists(pdf_dir):
        logger.warning(f"PDF directory not found: {pdf_dir}")
        return {}
    
    # Create a temporary directory for extracted CSV files
    temp_dir = os.path.join(pdf_dir, 'extracted')
    os.makedirs(temp_dir, exist_ok=True)
    
    # Process PDFs and extract to CSVs
    csv_files = process_pdf_directory(pdf_dir, temp_dir)
    
    if not csv_files:
        logger.warning("No transactions extracted from PDF files")
        return {}
    
    # Import the generated CSV files
    result = {}
    for csv_path in csv_files:
        try:
            source, count = import_csv_file(csv_path, interactive, full_import)
            if source:
                if source in result:
                    result[source] += count
                else:
                    result[source] = count
        except Exception as e:
            logger.error(f"Error importing extracted CSV {csv_path}: {e}")
    
    return result

def import_qfx_files(qfx_dir: str = None, interactive: bool = False, full_import: bool = False) -> Dict[str, int]:
    """
    Import transactions from QFX files.
    
    Args:
        qfx_dir: Directory containing QFX files (default: data/qfx)
        interactive: Whether to prompt user for source detection and column mapping
        full_import: Whether to perform a full import (ignore import history)
        
    Returns:
        Dictionary mapping source names to record counts
    """
    # Default QFX directory
    if qfx_dir is None:
        qfx_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'qfx')
    
    if not os.path.exists(qfx_dir):
        logger.warning(f"QFX directory not found: {qfx_dir}")
        return {}
    
    # Create a temporary directory for extracted CSV files
    temp_dir = os.path.join(qfx_dir, 'extracted')
    os.makedirs(temp_dir, exist_ok=True)
    
    # Process QFXs and extract to CSVs
    csv_files = process_qfx_directory(qfx_dir, temp_dir)
    
    if not csv_files:
        logger.warning("No transactions extracted from QFX files")
        return {}
    
    # Import the generated CSV files
    result = {}
    for csv_path in csv_files:
        try:
            source, count = import_csv_file(csv_path, interactive, full_import)
            if source:
                if source in result:
                    result[source] += count
                else:
                    result[source] = count
        except Exception as e:
            logger.error(f"Error importing extracted CSV {csv_path}: {e}")
    
    return result

def show_import_history() -> List[Dict]:
    """
    Show the import history from the database.
    
    Returns:
        List of import history records
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT source, filename, import_date, record_count 
        FROM import_log 
        ORDER BY import_date DESC
    ''')
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return results

def get_transaction_summary() -> Dict[str, Any]:
    """
    Get a summary of all transactions in the database.
    
    Returns:
        Dictionary with summary information
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get total record count
    cursor.execute("SELECT COUNT(*) FROM consolidated_transactions")
    record_count = cursor.fetchone()[0]
    
    # Get date range
    cursor.execute("""
        SELECT 
            MIN(date_posted) as first_date, 
            MAX(date_posted) as last_date
        FROM consolidated_transactions
    """)
    date_range = cursor.fetchone()
    
    # Get source breakdown
    cursor.execute("""
        SELECT source, COUNT(*) as count
        FROM consolidated_transactions
        GROUP BY source
        ORDER BY count DESC
    """)
    sources = [dict(row) for row in cursor.fetchall()]
    
    # Get total amount
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as spending,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income
        FROM consolidated_transactions
    """)
    amount_summary = cursor.fetchone()
    
    # Get classification stats
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN rental_related = 1 THEN 1 ELSE 0 END) as rental_count,
            SUM(CASE WHEN recurring = 1 THEN 1 ELSE 0 END) as recurring_count,
            SUM(CASE WHEN subscription = 1 THEN 1 ELSE 0 END) as subscription_count,
            SUM(CASE WHEN tax_deductible = 1 THEN 1 ELSE 0 END) as tax_deductible_count,
            SUM(CASE WHEN equipment_tools = 1 THEN 1 ELSE 0 END) as equipment_count
        FROM consolidated_transactions
    """)
    classification = cursor.fetchone()
    
    # Get top categories
    cursor.execute("""
        SELECT expense_category, COUNT(*) as count, SUM(amount) as total
        FROM consolidated_transactions
        WHERE expense_category IS NOT NULL AND expense_category != ''
        GROUP BY expense_category
        ORDER BY ABS(SUM(amount)) DESC
        LIMIT 10
    """)
    top_categories = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        'record_count': record_count,
        'date_range': {
            'first_date': date_range['first_date'],
            'last_date': date_range['last_date']
        },
        'sources': sources,
        'amount_summary': {
            'spending': amount_summary['spending'],
            'income': amount_summary['income'],
            'net': amount_summary['income'] + amount_summary['spending']
        },
        'classification': {
            'rental_count': classification['rental_count'],
            'recurring_count': classification['recurring_count'],
            'subscription_count': classification['subscription_count'],
            'tax_deductible_count': classification['tax_deductible_count'],
            'equipment_count': classification['equipment_count']
        },
        'top_categories': top_categories
    }

if __name__ == "__main__":
    # Initialize database
    initialize_database()
    
    # Example usage
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    
    print("Importing CSV files...")
    results = import_all_csv_files(data_dir)
    for source, count in results.items():
        print(f"  - {source}: {count} records")
    
    print("\nImporting PDF files...")
    pdf_results = import_pdf_files()
    for source, count in pdf_results.items():
        print(f"  - {source}: {count} records")
    
    print("\nImporting QFX files...")
    qfx_results = import_qfx_files()
    for source, count in qfx_results.items():
        print(f"  - {source}: {count} records")
    
    print("\nImport history:")
    history = show_import_history()
    for record in history:
        print(f"  - {record['source']}: {record['filename']} ({record['record_count']} records on {record['import_date']})")
    
    print("\nTransaction summary:")
    summary = get_transaction_summary()
    print(f"  - Total records: {summary['record_count']}")
    print(f"  - Date range: {summary['date_range']['first_date']} to {summary['date_range']['last_date']}")
    print(f"  - Spending: ${abs(summary['amount_summary']['spending']):.2f}")
    print(f"  - Income: ${summary['amount_summary']['income']:.2f}")
    print(f"  - Net: ${summary['amount_summary']['net']:.2f}")
    print(f"  - Classifications:")
    for key, value in summary['classification'].items():
        print(f"    - {key.replace('_count', '')}: {value}")
    print("  - Top categories:")
    for cat in summary['top_categories']:
        print(f"    - {cat['expense_category']}: ${abs(cat['total']):.2f} ({cat['count']} transactions)")