import pandas as pd
import os
import sqlite3
import re
import numpy as np
import datetime
import argparse
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
from sklearn.pipeline import Pipeline
from typing import Dict, List, Tuple, Optional, Any, Union

# Configuration constants
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(BASE_DIR, 'db', 'transactions.db')
MODEL_DIR = os.path.join(BASE_DIR, 'models')

# ---------------------------
# Data Cleaning and Preparation
# ---------------------------

def clean_column_name(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize column names by converting to lowercase and replacing spaces and special chars with underscores."""
    df.columns = df.columns.str.replace(' ', '_').str.lower()
    df.columns = [re.sub(r'\W+', '_', col.strip()) for col in df.columns]
    return df


def clean_transaction_data(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing values and standardize transaction data."""
    df.fillna({'Amount': 0}, inplace=True)
    return df


def find_source_in_filename(filename: str) -> str:
    """
    Identify the source financial institution from the CSV filename.
    Uses filename pattern matching to categorize the data source.
    
    Args:
        filename: The filename to analyze
        
    Returns:
        Source identifier (chase, discover, amex_plat, etc.)
    """
    filename = filename.lower()
    print(f"Processing filename: {filename}")
    
    # Bank/source detection logic
    if 'home' in filename and 'depot' in filename:
        print(f"Matched 'home_depot' in {filename}")
        return 'home_depot'
    elif 'chase' in filename and not ('pestchaser' in filename or 'chaser' in filename):
        print(f"Matched 'chase' in {filename}")
        return 'chase'
    elif "discover" in filename:
        print(f"Matched 'discover' in {filename}")
        return 'discover' 
    elif "amex" in filename and 'plat' in filename:
        print(f"Matched 'amex_plat' in {filename}")
        return 'amex_plat'
    elif 'amex' in filename and 'rose' in filename:
        print(f"Matched 'amex_rose' in {filename}")
        return 'amex_rose'
    else:
        print(f"No match for {filename}, using filename as source")
        return filename


def get_date_column_for_source(source: str) -> Optional[str]:
    """
    Return the correct date column name for each data source.
    
    Args:
        source: The financial institution source identifier
        
    Returns:
        Column name for transaction dates
    """
    date_columns = {
        'chase': 'date_posted',
        'discover': 'date_posted',  # or 'date_trans' depending on preference
        'amex_plat': 'date_posted',
        'amex_rose': 'date_posted',
        'home_depot': 'date'
    }
    return date_columns.get(source)


def rename_columns(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """
    Rename columns using the mapping dictionaries for each financial institution.
    
    Args:
        df: The DataFrame to rename columns for
        source: The source identifier (chase, discover, etc.)
        
    Returns:
        DataFrame with standardized column names
    """
    column_mappings = {
        "chase": {
            'posting_date': 'date_posted',
            'type': 'category',
            'amount': 'amount',
            'description': 'description',
            'details': 'details',
            'balance': 'balance',
            'check_or_slip': 'check'
        },
        "discover": {
            'post_date': 'date_posted',
            'trans_date': 'date_trans',
            'amount': 'amount',
            'description': 'description',
            'category': 'category',
            'balance': 'balance'
        },
        "amex_plat": {
            'date': 'date_posted',
            'amount': 'amount',
            'description': 'description',
            'category': 'category',
            'extended_details': 'details'
        },
        "amex_rose": {
            'date': 'date_posted',
            'amount': 'amount',
            'description': 'description',
            'category': 'category',
            'extended_details': 'details'
        },
        "home_depot": {
            'date': 'date_posted',
            'sku_description': 'description',
            'unit_price': 'amount',
            'department_name': 'category',
            'job_name': 'details'
        }
    }

    # Clean column names before attempting to map them
    df = clean_column_name(df)

    if source in column_mappings:
        # Create a copy of the mapping since we'll modify it
        mapping = column_mappings[source].copy()
        
        # Only apply mappings for columns that actually exist in the dataframe
        valid_mapping = {col: target for col, target in mapping.items() if col in df.columns}
        
        if valid_mapping:
            df.rename(columns=valid_mapping, inplace=True)
        else:
            print(f"Warning: No valid column mappings found for source '{source}'")
            print(f"Available columns: {df.columns.tolist()}")
    else:
        print(f"Warning: No column mapping defined for source '{source}'")
    
    return df


# ---------------------------
# Database Operations
# ---------------------------

def create_import_log_table(conn: sqlite3.Connection) -> None:
    """Create a table to track transaction import history if it doesn't exist."""
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS import_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        filename TEXT NOT NULL,
        last_import_date TEXT NOT NULL,
        import_timestamp TEXT NOT NULL,
        num_transactions INTEGER NOT NULL
    )
    """)
    conn.commit()


def get_last_import_date(conn: sqlite3.Connection, source: str) -> Optional[str]:
    """
    Get the most recent import date for a given source.
    
    Args:
        conn: SQLite database connection
        source: Source identifier
        
    Returns:
        Date string of the last import or None
    """
    cursor = conn.cursor()
    cursor.execute("""
    SELECT last_import_date FROM import_log 
    WHERE source = ? 
    ORDER BY import_timestamp DESC LIMIT 1
    """, (source,))
    result = cursor.fetchone()
    return result[0] if result else None


def log_import(conn: sqlite3.Connection, source: str, filename: str, 
              last_date: str, num_transactions: int) -> None:
    """
    Log an import operation to the database.
    
    Args:
        conn: SQLite database connection
        source: Source identifier
        filename: Original filename
        last_date: Date of the most recent transaction
        num_transactions: Number of transactions imported
    """
    cursor = conn.cursor()
    import_timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
    INSERT INTO import_log 
    (source, filename, last_import_date, import_timestamp, num_transactions)
    VALUES (?, ?, ?, ?, ?)
    """, (source, filename, last_date, import_timestamp, num_transactions))
    conn.commit()


def prompt_for_source_name(filename: str) -> str:
    """
    Prompt user to provide a custom name for the source.
    Suggests a name based on the filename, but lets the user override it.
    
    Args:
        filename: The original filename
        
    Returns:
        User-provided source name
    """
    suggested_source = find_source_in_filename(filename)
    print(f"\nProcessing file: {filename}")
    print(f"Suggested source name: {suggested_source}")
    
    user_source = input(f"Enter source name (or press Enter to use '{suggested_source}'): ").strip()
    if not user_source:
        return suggested_source
    
    # Replace spaces and special characters with underscores
    user_source = re.sub(r'\W+', '_', user_source).lower()
    return user_source


def consolidate_transactions(db_path: str) -> None:
    """
    Consolidate transactions from all sources into a single table
    with a unified schema for analysis.
    
    Args:
        db_path: Path to the SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Drop existing consolidated table if needed
    cursor.execute("DROP TABLE IF EXISTS consolidated_transactions")

    # Create a unified schema
    cursor.execute("""
        CREATE TABLE consolidated_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_posted TEXT,
            description TEXT,
            amount REAL,
            category TEXT,
            details TEXT,
            source TEXT
        )
    """)

    # Get all tables in the database
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('sqlite_sequence', 'import_log', 'consolidated_transactions')")
    tables = cursor.fetchall()
    
    for table in tables:
        table_name = table[0]
        
        # Skip system tables
        if table_name.startswith('sqlite_'):
            continue
            
        print(f"Consolidating data from {table_name}...")
        
        try:
            # Check if the table has required columns - use quotes around table name for safety
            cursor.execute(f'PRAGMA table_info("{table_name}")')
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            # Skip tables without required columns
            required_columns = ['date_posted', 'description', 'amount']
            if not all(col in column_names for col in required_columns):
                print(f"Skipping {table_name}: Missing required columns")
                continue
            
            # Add optional columns with defaults if they don't exist
            category_col = 'category' if 'category' in column_names else "'Unknown' AS category"
            details_col = 'details' if 'details' in column_names else "NULL AS details"
            
            # Insert data from this source
            cursor.execute(f"""
                INSERT INTO consolidated_transactions 
                (date_posted, description, amount, category, details, source)
                SELECT date_posted, description, amount, {category_col}, {details_col}, '{table_name}'
                FROM "{table_name}"
            """)
            
            rows_added = cursor.rowcount
            print(f"Added {rows_added} transactions from {table_name}")
            
        except sqlite3.Error as e:
            print(f"Error consolidating {table_name}: {e}")
    
    # Get total transaction count
    cursor.execute("SELECT COUNT(*) FROM consolidated_transactions")
    total = cursor.fetchone()[0]
    print(f"Consolidated {total} transactions in total")

    conn.commit()
    conn.close()


def add_classification_columns(db_path: str) -> None:
    """
    Add columns for classification if they don't already exist.
    
    Args:
        db_path: Path to the SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # SQLite's ALTER TABLE doesn't support IF NOT EXISTS, so we use try/except.
    classification_columns = [
        ("rental_related", "INTEGER"),
        ("expense_category", "TEXT"),
        ("maintenance_upgrade", "TEXT"),
        ("recurring", "INTEGER"),      # Flag for recurring transactions
        ("recurring_group", "TEXT"),   # Group ID for recurring transactions
        ("recurring_freq", "TEXT"),    # Frequency (monthly, weekly, etc.)
        ("subscription", "INTEGER"),   # Flag for subscription services
        ("tax_deductible", "INTEGER"), # Flag for tax deductible expenses
        ("equipment_tools", "INTEGER"), # Flag for depreciable tools and equipment
        ("purchase_date", "TEXT"),     # For tracking depreciation start dates
        ("asset_value", "REAL"),       # Purchase value of the equipment/tool
        ("depreciation_years", "INTEGER"), # Expected years of depreciation
        ("notes", "TEXT")              # User notes about the transaction
    ]
    
    for col, col_type in classification_columns:
        try:
            cursor.execute(f"ALTER TABLE consolidated_transactions ADD COLUMN {col} {col_type};")
            print(f"Added column {col} to consolidated_transactions")
        except sqlite3.OperationalError:
            print(f"Column probably already exists: {col}")
            # Likely the column already exists
            pass
    conn.commit()
    conn.close()


def list_import_history(db_path: str) -> None:
    """
    List the import history from the import_log table.
    
    Args:
        db_path: Path to the SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
        SELECT source, filename, last_import_date, import_timestamp, num_transactions 
        FROM import_log ORDER BY import_timestamp DESC
        """)
        history = cursor.fetchall()
        
        if not history:
            print("No import history found")
        else:
            print("\n--- Import History ---")
            print(f"{'Source':<15} {'Last Import Date':<20} {'Import Time':<20} {'Transactions':<10} {'Filename'}")
            print("-" * 90)
            for entry in history:
                source, filename, last_date, timestamp, count = entry
                print(f"{source:<15} {last_date:<20} {timestamp:<20} {count:<10} {filename}")
    except sqlite3.OperationalError:
        print("Import log table doesn't exist yet. Run an import first.")
        
    conn.close()


def show_transaction_summary(db_path: str) -> None:
    """
    Show a summary of transactions in the database.
    
    Args:
        db_path: Path to the SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Show tables and counts
    cursor.execute("""
    SELECT name FROM sqlite_master 
    WHERE type='table' AND name NOT IN ('sqlite_sequence', 'import_log')
    """)
    tables = cursor.fetchall()
    
    print("\n--- Transaction Summary ---")
    print(f"{'Source':<15} {'Count':<8} {'Date Range'}")
    print("-" * 50)
    
    total_transactions = 0
    for table in tables:
        table_name = table[0]
        
        # Skip system tables
        if table_name.startswith('sqlite_'):
            continue
            
        try:
            # Check if this table has a date column
            cursor.execute(f'PRAGMA table_info("{table_name}")')
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            # Find the date column
            date_col = None
            for possible_col in ['date_posted', 'date', 'post_date', 'trans_date']:
                if possible_col in column_names:
                    date_col = possible_col
                    break
                    
            # Get count
            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
            count = cursor.fetchone()[0]
            total_transactions += count
            
            # Get date range if possible
            date_range = "N/A"
            if date_col:
                cursor.execute(f'SELECT MIN({date_col}), MAX({date_col}) FROM "{table_name}"')
                min_date, max_date = cursor.fetchone()
                if min_date and max_date:
                    date_range = f"{min_date} to {max_date}"
            
            print(f"{table_name:<15} {count:<8} {date_range}")
            
        except sqlite3.Error as e:
            print(f"{table_name:<15} Error: {e}")
    
    print("-" * 50)
    print(f"Total: {total_transactions} transactions")
    
    # If consolidated_transactions exists, show stats
    cursor.execute("""
    SELECT COUNT(*) 
    FROM sqlite_master 
    WHERE type='table' AND name='consolidated_transactions'
    """)
    
    if cursor.fetchone()[0] > 0:
        print("\n--- Consolidated Transactions ---")
        
        # Count by source
        cursor.execute("""
        SELECT source, COUNT(*) as count
        FROM consolidated_transactions
        GROUP BY source
        ORDER BY count DESC
        """)
        
        sources = cursor.fetchall()
        if sources:
            print(f"{'Source':<15} {'Count':<8}")
            print("-" * 25)
            for source, count in sources:
                print(f"{source:<15} {count:<8}")
        
        # Classification progress
        try:
            # Check if the new columns exist
            cursor.execute("PRAGMA table_info(consolidated_transactions)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            # Check for different classification types
            metrics = []
            if 'rental_related' in column_names:
                metrics.append(("Rental", "SUM(CASE WHEN rental_related = 1 THEN 1 ELSE 0 END)"))
            if 'recurring' in column_names:
                metrics.append(("Recurring", "SUM(CASE WHEN recurring = 1 THEN 1 ELSE 0 END)"))
            if 'subscription' in column_names:
                metrics.append(("Subscription", "SUM(CASE WHEN subscription = 1 THEN 1 ELSE 0 END)"))
            if 'tax_deductible' in column_names:
                metrics.append(("Tax Deductible", "SUM(CASE WHEN tax_deductible = 1 THEN 1 ELSE 0 END)"))
            if 'equipment_tools' in column_names:
                metrics.append(("Equipment/Tools", "SUM(CASE WHEN equipment_tools = 1 THEN 1 ELSE 0 END)"))
                
            # Create a combined query
            if metrics:
                query = "SELECT COUNT(*) as total, " + ", ".join([m[1] + " as " + m[0].lower() for m in metrics]) + " FROM consolidated_transactions"
                cursor.execute(query)
                result = cursor.fetchone()
                
                total = result[0]
                print("\n--- Classification Progress ---")
                print(f"Total transactions: {total}")
                for i, metric in enumerate(metrics):
                    count = result[i+1] or 0
                    percent = count / total * 100 if total > 0 else 0
                    print(f"{metric[0]}: {count}/{total} ({percent:.1f}%)")
            
            # Check for unclassified transactions
            cursor.execute("""
            SELECT COUNT(*) FROM consolidated_transactions 
            WHERE rental_related IS NULL 
            AND recurring IS NULL 
            AND subscription IS NULL
            AND tax_deductible IS NULL
            AND equipment_tools IS NULL
            """)
            unclassified = cursor.fetchone()[0]
            if unclassified:
                percent = unclassified / total * 100 if total > 0 else 0
                print(f"Unclassified: {unclassified}/{total} ({percent:.1f}%)")
                
        except sqlite3.Error as e:
            print(f"Error getting classification stats: {e}")
    
    conn.close()


# ---------------------------
# Data Import and CSV Processing
# ---------------------------

def initialize_database(db_path: str) -> sqlite3.Connection:
    """
    Initialize database with all required tables for the application.
    
    Args:
        db_path: Path to the SQLite database
        
    Returns:
        The database connection
    """
    # Create database directory if it doesn't exist
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    
    # Create import log table
    create_import_log_table(conn)
    
    # Create budget tables
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        period TEXT NOT NULL,  -- 'monthly' or 'annual'
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    
    # Budget categories table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS budget_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        budget_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        FOREIGN KEY (budget_id) REFERENCES budgets (id) ON DELETE CASCADE
    )
    """)
    
    # Goals table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT NOT NULL,  -- 'savings' or 'debt_repayment'
        target_amount REAL NOT NULL,
        current_amount REAL NOT NULL DEFAULT 0,
        start_date TEXT NOT NULL,
        target_date TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        notes TEXT
    )
    """)
    
    # Goal transactions table (to track contributions/payments)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS goal_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        goal_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        date TEXT NOT NULL,
        notes TEXT,
        FOREIGN KEY (goal_id) REFERENCES goals (id) ON DELETE CASCADE
    )
    """)
    
    # Recurring transactions for cash flow forecasting
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS recurring_forecasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        description TEXT NOT NULL,
        amount REAL NOT NULL,
        type TEXT NOT NULL,  -- 'income' or 'expense'
        frequency TEXT NOT NULL,  -- 'daily', 'weekly', 'biweekly', 'monthly', 'quarterly', 'annual'
        day_of_month INTEGER,  -- for monthly recurring items
        day_of_week INTEGER,   -- for weekly recurring items
        start_date TEXT NOT NULL,
        end_date TEXT,  -- NULL if no end date
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        category TEXT,
        source TEXT,
        notes TEXT
    )
    """)
    
    conn.commit()
    return conn

def ingest_csv_to_db(csv_dir: str, db_path: str, incremental: bool = True, 
                     interactive: bool = False) -> None:
    """
    Import CSV files into the database. 
    
    Args:
        csv_dir: Directory containing CSV files
        db_path: Path to the SQLite database
        incremental: If True, only import transactions newer than the last import date
        interactive: If True, prompt for custom source names
    """
    # Initialize database and all required tables
    conn = initialize_database(db_path)

    # List all CSV files
    csv_files = []
    for filename in os.listdir(csv_dir):
        if filename.lower().endswith('.csv'):
            csv_files.append(filename)
    
    if not csv_files:
        print("No CSV files found in directory")
        conn.close()
        return
    
    print(f"Found {len(csv_files)} CSV files to process")
    
    for filename in csv_files:
        original_filename = filename
        filename = filename.lower()
        
        if interactive:
            # Ask user for source name
            source = prompt_for_source_name(filename)
        else:
            source = find_source_in_filename(filename)

        if not source:
            print(f"Skipping {filename}: Unrecognized source and no name provided")
            continue
        
        print(f"Processing {filename} as source '{source}'")    
        file_path = os.path.join(csv_dir, original_filename)

        # Load the CSV data
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            continue
            
        # Show column preview
        print(f"\nColumn preview for {filename}:")
        print(f"Available columns: {', '.join(df.columns.tolist())}")
        print(f"First 2 rows:")
        print(df.head(2))
        
        if interactive:
            # Let user map columns
            print("\nColumn mapping for standard fields (press Enter to skip):")
            date_col = input("Which column contains the transaction date? ").strip() or None
            desc_col = input("Which column contains the transaction description? ").strip() or None
            amount_col = input("Which column contains the transaction amount? ").strip() or None
            category_col = input("Which column contains the transaction category? ").strip() or None
            
            # Create custom mapping
            custom_mapping = {}
            if date_col and date_col in df.columns:
                custom_mapping[date_col] = 'date_posted'
            if desc_col and desc_col in df.columns:
                custom_mapping[desc_col] = 'description'
            if amount_col and amount_col in df.columns:
                custom_mapping[amount_col] = 'amount'
            if category_col and category_col in df.columns:
                custom_mapping[category_col] = 'category'
                
            # Apply custom mapping if provided
            if custom_mapping:
                df.rename(columns=custom_mapping, inplace=True)
            else:
                # Fall back to automatic column mapping
                df = rename_columns(df, source)
        else:
            # Use automatic column mapping
            df = rename_columns(df, source)
        
        # Get the date column name based on source (varies by bank)
        date_col = get_date_column_for_source(source) if not interactive else 'date_posted'
        if not date_col or date_col not in df.columns:
            print(f"Warning: Could not identify date column for {source}, using first column")
            date_col = df.columns[0]
        
        # Convert the date column to datetime
        try:
            df[date_col] = pd.to_datetime(df[date_col])
            # Sort by date so we can track the most recent transaction
            df = df.sort_values(by=date_col)
        except Exception as e:
            print(f"Warning: Could not convert {date_col} to datetime for {source}: {e}")
        
        # If incremental import, filter by last import date
        if incremental:
            last_import_date = get_last_import_date(conn, source)
            
            if last_import_date:
                try:
                    last_date = pd.to_datetime(last_import_date)
                    print(f"Filtering {source} transactions after {last_date}")
                    # Only keep transactions newer than the last import
                    df = df[df[date_col] > last_date]
                except Exception as e:
                    print(f"Warning: Could not parse last import date {last_import_date}: {e}")
        
        original_count = len(df)
        if original_count == 0:
            print(f"No new transactions to import for {source}")
            continue
            
        # Get the most recent transaction date for logging
        most_recent_date = df[date_col].max().strftime('%Y-%m-%d')
        
        # Append to the existing table if incremental, otherwise replace
        if_exists = 'append' if incremental else 'replace'
        df.to_sql(source, conn, if_exists=if_exists, index=False)
        
        # Log this import
        log_import(conn, source, filename, most_recent_date, original_count)
        
        print(f"Imported {original_count} transactions from {filename} into table '{source}'")
    
    conn.commit()
    conn.close()


# ---------------------------
# Transaction Classification
# ---------------------------

def sample_transactions(db_path: str, fraction: float = 0.10) -> List[Tuple]:
    """
    Take a sample from the transactions for testing or model training.
    
    Args:
        db_path: Path to the SQLite database
        fraction: Fraction of transactions to sample (0-1)
        
    Returns:
        List of transaction tuples
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Count the total transactions in the consolidated table
    cursor.execute("SELECT COUNT(*) FROM consolidated_transactions")
    total = cursor.fetchone()[0]
    
    # Calculate sample size (ensuring at least one row is returned)
    sample_size = max(1, int(total * fraction))
    print(f"Total transactions: {total}, sampling: {sample_size}")

    # Randomly select sample_size transactions
    cursor.execute(
        "SELECT * FROM consolidated_transactions ORDER BY RANDOM() LIMIT ?",
        (sample_size,)
    )
    sample = cursor.fetchall()
    conn.close()
    return sample


def detect_recurring_transactions(db_path: str) -> int:
    """
    Detect recurring transactions by finding similar descriptions and amounts on a monthly basis.
    
    Args:
        db_path: Path to the SQLite database
        
    Returns:
        Number of recurring transactions identified
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Use row factory for named columns
    cursor = conn.cursor()
    
    print("Detecting recurring transactions...")
    
    # First, extract unique transaction descriptions
    cursor.execute("""
        SELECT DISTINCT description 
        FROM consolidated_transactions
        WHERE description IS NOT NULL AND description != ''
    """)
    
    all_descriptions = [row['description'] for row in cursor.fetchall()]
    
    # Count of recurring transactions identified
    recurring_count = 0
    
    # Process each description
    for desc in all_descriptions:
        # Get transactions with this description
        cursor.execute("""
            SELECT id, date_posted, description, amount, source
            FROM consolidated_transactions
            WHERE description = ?
            ORDER BY date_posted
        """, (desc,))
        
        transactions = cursor.fetchall()
        
        # Skip if only one transaction with this description
        if len(transactions) < 2:
            continue
            
        # Convert date_posted to datetime objects and group by month
        months = {}
        for txn in transactions:
            try:
                date = pd.to_datetime(txn['date_posted'])
                month_key = f"{date.year}-{date.month:02d}"
                
                if month_key not in months:
                    months[month_key] = []
                    
                months[month_key].append(txn)
            except:
                continue
        
        # Check if there are similar transactions in multiple months
        if len(months) >= 2:
            # Calculate average amount
            amounts = [txn['amount'] for txn in transactions]
            avg_amount = sum(amounts) / len(amounts)
            
            # Calculate standard deviation
            std_amount = (sum((a - avg_amount) ** 2 for a in amounts) / len(amounts)) ** 0.5
            
            # If standard deviation is small relative to average (consistent amounts)
            # or there are >= 3 months with the same description, mark as recurring
            is_recurring = (std_amount / abs(avg_amount) < 0.1 if avg_amount != 0 else False) or len(months) >= 3
            
            if is_recurring:
                # Generate a recurring group ID based on the first few chars of description
                group_id = re.sub(r'\W+', '', desc)[:20].upper()
                
                # Mark all these transactions as recurring
                for txn in transactions:
                    cursor.execute("""
                        UPDATE consolidated_transactions
                        SET recurring = 1,
                            recurring_group = ?,
                            recurring_freq = 'MONTHLY'
                        WHERE id = ?
                    """, (group_id, txn['id']))
                    recurring_count += 1
    
    conn.commit()
    print(f"Identified {recurring_count} recurring transactions in {len(all_descriptions)} unique descriptions")
    conn.close()
    
    return recurring_count


def interactive_classification(db_path: str, sample_size: int = 5, mode: str = 'all') -> None:
    """
    Pull a sample of unlabeled transactions and let the user classify them.
    
    Args:
        db_path: Path to the SQLite database
        sample_size: Number of transactions to classify in one batch
        mode: Classification mode - 'all', 'rental', 'recurring', 'subscription', 'equipment', etc.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Build the WHERE clause based on the mode
    where_clause = ""
    if mode == 'rental':
        where_clause = "WHERE rental_related IS NULL"
    elif mode == 'recurring':
        where_clause = "WHERE recurring IS NULL"
    elif mode == 'subscription':
        where_clause = "WHERE subscription IS NULL"
    elif mode == 'tax':
        where_clause = "WHERE tax_deductible IS NULL"
    elif mode == 'equipment':
        where_clause = "WHERE equipment_tools IS NULL"
    else:  # 'all' or default
        where_clause = "WHERE rental_related IS NULL OR recurring IS NULL OR subscription IS NULL OR equipment_tools IS NULL"
    
    # Get a sample of transactions that have not been fully classified
    query = f"""
        SELECT id, date_posted, description, amount, source
        FROM consolidated_transactions 
        {where_clause}
        ORDER BY date_posted DESC
        LIMIT ?
    """
    
    cursor.execute(query, (sample_size,))
    transactions = cursor.fetchall()

    if not transactions:
        print(f"No transactions found for {mode} classification.")
        conn.close()
        return

    for txn in transactions:
        txn_id, date, description, amount, source = txn
        print(f"\nTransaction ID: {txn_id}")
        print(f"Date: {date}")
        print(f"Source: {source}")
        print(f"Description: {description}")
        print(f"Amount: {amount}")
        
        updates = {}
        
        # Only ask relevant questions based on mode
        if mode in ['all', 'rental']:
            rental_input = input("Is this a rental property expense? (y/n/s=skip): ").strip().lower()
            if rental_input != 's':
                updates['rental_related'] = 1 if rental_input == 'y' else 0
                
                if rental_input == 'y':
                    mu_input = input("Is it an upgrade or maintenance? (u=upgrade/m=maintenance/s=skip): ").strip().lower()
                    if mu_input != 's':
                        if mu_input == "u":
                            updates['maintenance_upgrade'] = "Upgrade"
                        elif mu_input == "m":
                            updates['maintenance_upgrade'] = "Maintenance"

        if mode in ['all', 'recurring']:
            recurring_input = input("Is this a recurring transaction? (y/n/s=skip): ").strip().lower()
            if recurring_input != 's':
                updates['recurring'] = 1 if recurring_input == 'y' else 0
                
                if recurring_input == 'y':
                    freq_input = input("Frequency (m=monthly/w=weekly/q=quarterly/y=yearly/s=skip): ").strip().lower()
                    if freq_input != 's':
                        freq_map = {'m': 'MONTHLY', 'w': 'WEEKLY', 'q': 'QUARTERLY', 'y': 'YEARLY'}
                        updates['recurring_freq'] = freq_map.get(freq_input, 'UNKNOWN')
                    
                    group_input = input("Recurring group name (or enter for auto-generate): ").strip()
                    if group_input:
                        updates['recurring_group'] = group_input
                    else:
                        # Auto-generate a group name from the description
                        group_id = re.sub(r'\W+', '', description)[:20].upper()
                        updates['recurring_group'] = group_id

        if mode in ['all', 'subscription']:
            sub_input = input("Is this a subscription service? (y/n/s=skip): ").strip().lower()
            if sub_input != 's':
                updates['subscription'] = 1 if sub_input == 'y' else 0
        
        if mode in ['all', 'tax']:
            tax_input = input("Is this tax deductible? (y/n/s=skip): ").strip().lower()
            if tax_input != 's':
                updates['tax_deductible'] = 1 if tax_input == 'y' else 0
        
        if mode in ['all', 'equipment']:
            equip_input = input("Is this depreciable equipment or a tool? (y/n/s=skip): ").strip().lower()
            if equip_input != 's':
                updates['equipment_tools'] = 1 if equip_input == 'y' else 0
                
                if equip_input == 'y':
                    # Capture purchase date (use transaction date as default)
                    purchase_date = input(f"Purchase date [{date}] (YYYY-MM-DD or s=skip): ").strip()
                    if purchase_date != 's':
                        updates['purchase_date'] = purchase_date if purchase_date else date
                    
                    # Capture asset value (use amount as default)
                    asset_value = input(f"Asset value [{amount}] (or s=skip): ").strip()
                    if asset_value != 's':
                        try:
                            updates['asset_value'] = float(asset_value) if asset_value else amount
                        except ValueError:
                            print("Invalid value, using transaction amount")
                            updates['asset_value'] = amount
                    
                    # Capture depreciation years
                    dep_years = input("Depreciation period in years (or s=skip): ").strip()
                    if dep_years != 's':
                        try:
                            updates['depreciation_years'] = int(dep_years) if dep_years else None
                        except ValueError:
                            print("Invalid value, skipping")
        
        if mode in ['all']:
            category_input = input("Enter expense category (or s=skip): ").strip()
            if category_input != 's':
                updates['expense_category'] = category_input
                
            notes_input = input("Additional notes (or s=skip): ").strip()
            if notes_input != 's':
                updates['notes'] = notes_input

        # Only update if we have something to update
        if updates:
            # Build the SET clause dynamically
            set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
            values = list(updates.values()) + [txn_id]  # Add txn_id at the end for the WHERE clause
            
            # Execute the UPDATE
            cursor.execute(f"""
                UPDATE consolidated_transactions
                SET {set_clause}
                WHERE id = ?
            """, values)
            conn.commit()
            print(f"Transaction {txn_id} updated with {', '.join(updates.keys())}.")
        else:
            print(f"Transaction {txn_id} skipped.")

    # Show how many transactions are left to classify
    remaining_counts = {}
    for field in ['rental_related', 'recurring', 'subscription', 'tax_deductible', 'equipment_tools']:
        cursor.execute(f"SELECT COUNT(*) FROM consolidated_transactions WHERE {field} IS NULL")
        remaining_counts[field] = cursor.fetchone()[0]
    
    print("\nRemaining transactions to classify:")
    print(f"Rental: {remaining_counts['rental_related']}")
    print(f"Recurring: {remaining_counts['recurring']}")
    print(f"Subscription: {remaining_counts['subscription']}")
    print(f"Tax Deductible: {remaining_counts['tax_deductible']}")
    print(f"Equipment/Tools: {remaining_counts['equipment_tools']}")
    
    conn.close()


# ---------------------------
# Budget Management
# ---------------------------

def create_budget(db_path: str) -> None:
    """
    Create a new budget by gathering user input for budget period, 
    categories and amounts.
    
    Args:
        db_path: Path to the SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n=== Create New Budget ===")
    
    # Get budget details
    name = input("Budget name: ").strip()
    
    period = ''
    while period not in ['monthly', 'annual']:
        period = input("Budget period (monthly/annual): ").strip().lower()
    
    # Get start and end dates
    valid_date = False
    while not valid_date:
        start_date_str = input("Start date (YYYY-MM-DD): ").strip()
        try:
            start_date = pd.to_datetime(start_date_str)
            valid_date = True
        except:
            print("Invalid date format. Please use YYYY-MM-DD.")
    
    valid_date = False
    while not valid_date:
        end_date_str = input("End date (YYYY-MM-DD): ").strip()
        try:
            end_date = pd.to_datetime(end_date_str)
            if end_date > start_date:
                valid_date = True
            else:
                print("End date must be after start date.")
        except:
            print("Invalid date format. Please use YYYY-MM-DD.")
    
    # Get categories from existing transactions
    print("\nFetching categories from your transactions...")
    try:
        cursor.execute("""
        SELECT DISTINCT category 
        FROM consolidated_transactions 
        WHERE category IS NOT NULL AND category != ''
        """)
        categories = [row[0] for row in cursor.fetchall()]
        print("Found categories:", ', '.join(categories[:10]) + ("..." if len(categories) > 10 else ""))
    except sqlite3.Error:
        categories = []
        print("No categories found or transactions table not available.")
    
    # Create the budget
    current_timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
    INSERT INTO budgets 
    (name, start_date, end_date, period, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (name, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), 
         period, current_timestamp, current_timestamp))
    
    budget_id = cursor.lastrowid
    print(f"\nBudget '{name}' created with ID {budget_id}.")
    
    # Add budget categories
    print("\nNow let's add budget categories and amounts.")
    print("Enter an empty category name when done.")
    
    total_budget = 0
    
    while True:
        # Show suggested categories
        if categories:
            print("\nSuggested categories:", ', '.join(categories[:5]))
        
        category = input("\nCategory (or empty to finish): ").strip()
        if not category:
            break
            
        valid_amount = False
        while not valid_amount:
            try:
                amount = float(input(f"Amount for {category}: $").strip())
                valid_amount = True
                total_budget += amount
            except ValueError:
                print("Please enter a valid number.")
        
        cursor.execute("""
        INSERT INTO budget_categories
        (budget_id, category, amount)
        VALUES (?, ?, ?)
        """, (budget_id, category, amount))
        
        # Remove this category from suggestions
        if category in categories:
            categories.remove(category)
    
    conn.commit()
    print(f"\nBudget completed with {total_budget:.2f} total across all categories.")
    conn.close()


def show_budgets(db_path: str) -> None:
    """
    Display a list of all budgets and their details.
    
    Args:
        db_path: Path to the SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n=== Your Budgets ===")
    
    # Get all budgets
    cursor.execute("""
    SELECT id, name, start_date, end_date, period
    FROM budgets
    ORDER BY start_date DESC
    """)
    
    budgets = cursor.fetchall()
    
    if not budgets:
        print("No budgets found. Create one with --create-budget")
        conn.close()
        return
    
    for budget in budgets:
        budget_id, name, start_date, end_date, period = budget
        
        # Get total budget amount
        cursor.execute("""
        SELECT SUM(amount) FROM budget_categories
        WHERE budget_id = ?
        """, (budget_id,))
        
        total = cursor.fetchone()[0] or 0
        
        # Get actual spending for this period
        try:
            cursor.execute("""
            SELECT SUM(amount) 
            FROM consolidated_transactions
            WHERE date_posted BETWEEN ? AND ?
            """, (start_date, end_date))
            
            actual_spent = cursor.fetchone()[0] or 0
            
            # Calculate remaining and percentage
            remaining = total - actual_spent
            percent_used = (actual_spent / total * 100) if total > 0 else 0
            
            print(f"\nBudget ID: {budget_id}")
            print(f"Name: {name}")
            print(f"Period: {period.capitalize()}, {start_date} to {end_date}")
            print(f"Total Budget: ${total:.2f}")
            print(f"Spent: ${actual_spent:.2f} ({percent_used:.1f}%)")
            print(f"Remaining: ${remaining:.2f}")
            
        except sqlite3.Error:
            print(f"\nBudget ID: {budget_id}")
            print(f"Name: {name}")
            print(f"Period: {period.capitalize()}, {start_date} to {end_date}")
            print(f"Total Budget: ${total:.2f}")
            print("Actual spending data not available.")
        
        # Show top 3 categories
        cursor.execute("""
        SELECT category, amount
        FROM budget_categories
        WHERE budget_id = ?
        ORDER BY amount DESC
        LIMIT 3
        """, (budget_id,))
        
        top_categories = cursor.fetchall()
        if top_categories:
            print("Top Categories:")
            for category, amount in top_categories:
                print(f"  - {category}: ${amount:.2f}")
        
        print("-" * 40)
    
    conn.close()


def compare_budget_vs_actual(db_path: str, budget_id: int) -> None:
    """
    Compare a specific budget against actual spending,
    showing detailed breakdown by category.
    
    Args:
        db_path: Path to the SQLite database
        budget_id: ID of the budget to analyze
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get budget information
    cursor.execute("""
    SELECT name, start_date, end_date, period
    FROM budgets
    WHERE id = ?
    """, (budget_id,))
    
    budget = cursor.fetchone()
    if not budget:
        print(f"Budget with ID {budget_id} not found.")
        conn.close()
        return
    
    name, start_date, end_date, period = budget
    
    print(f"\n=== Budget Analysis: {name} ===")
    print(f"Period: {period.capitalize()}, {start_date} to {end_date}")
    
    # Get all categories in this budget
    cursor.execute("""
    SELECT category, amount
    FROM budget_categories
    WHERE budget_id = ?
    ORDER BY amount DESC
    """, (budget_id,))
    
    categories = cursor.fetchall()
    if not categories:
        print("No categories found in this budget.")
        conn.close()
        return
    
    print("\nCategory Breakdown:")
    print(f"{'Category':<25} {'Budgeted':<12} {'Actual':<12} {'Diff':<12} {'% Used':<10}")
    print("-" * 70)
    
    total_budgeted = 0
    total_actual = 0
    
    for category, budgeted in categories:
        total_budgeted += budgeted
        
        # Get actual spending for this category in the budget period
        try:
            cursor.execute("""
            SELECT SUM(amount) 
            FROM consolidated_transactions
            WHERE category = ? AND date_posted BETWEEN ? AND ?
            """, (category, start_date, end_date))
            
            actual = cursor.fetchone()[0] or 0
            total_actual += actual
            
            diff = budgeted - actual
            percent = (actual / budgeted * 100) if budgeted > 0 else 0
            
            # Highlight overspending
            status = "!" if actual > budgeted else " "
            
            print(f"{category:<25} ${budgeted:<10.2f} ${actual:<10.2f} ${diff:<10.2f} {percent:<8.1f}% {status}")
            
        except sqlite3.Error:
            print(f"{category:<25} ${budgeted:<10.2f} {'N/A':<10} {'N/A':<10} {'N/A':<8}")
    
    print("-" * 70)
    
    # Show totals
    diff = total_budgeted - total_actual
    percent = (total_actual / total_budgeted * 100) if total_budgeted > 0 else 0
    status = "!" if total_actual > total_budgeted else " "
    
    print(f"{'TOTAL':<25} ${total_budgeted:<10.2f} ${total_actual:<10.2f} ${diff:<10.2f} {percent:<8.1f}% {status}")
    
    # Show uncategorized spending
    try:
        cursor.execute("""
        SELECT SUM(amount) 
        FROM consolidated_transactions
        WHERE (category IS NULL OR category = '') AND date_posted BETWEEN ? AND ?
        """, (start_date, end_date))
        
        uncategorized = cursor.fetchone()[0] or 0
        if uncategorized > 0:
            print(f"\nNote: ${uncategorized:.2f} in uncategorized spending not included in budget comparison.")
    except sqlite3.Error:
        pass
    
    conn.close()


# ---------------------------
# Goals Management 
# ---------------------------

def add_goal(db_path: str) -> None:
    """
    Add a new financial goal (savings or debt repayment).
    
    Args:
        db_path: Path to the SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n=== Create New Financial Goal ===")
    
    # Get goal details
    name = input("Goal name: ").strip()
    
    goal_type = ''
    while goal_type not in ['savings', 'debt_repayment']:
        goal_type = input("Goal type (savings/debt_repayment): ").strip().lower()
    
    valid_amount = False
    while not valid_amount:
        try:
            target_amount = float(input("Target amount: $").strip())
            if target_amount <= 0:
                print("Amount must be greater than zero.")
            else:
                valid_amount = True
        except ValueError:
            print("Please enter a valid number.")
    
    valid_amount = False
    while not valid_amount:
        try:
            current_amount = float(input("Current progress: $").strip())
            if current_amount < 0:
                print("Amount must not be negative.")
            elif current_amount > target_amount:
                print("Current amount cannot exceed target amount.")
            else:
                valid_amount = True
        except ValueError:
            print("Please enter a valid number.")
    
    # Get dates
    valid_date = False
    while not valid_date:
        start_date_str = input("Start date (YYYY-MM-DD or today): ").strip()
        if start_date_str.lower() == 'today':
            start_date = pd.Timestamp.now().strftime('%Y-%m-%d')
            valid_date = True
        else:
            try:
                start_date = pd.to_datetime(start_date_str).strftime('%Y-%m-%d')
                valid_date = True
            except:
                print("Invalid date format. Please use YYYY-MM-DD.")
    
    valid_date = False
    while not valid_date:
        target_date_str = input("Target completion date (YYYY-MM-DD): ").strip()
        try:
            target_date = pd.to_datetime(target_date_str)
            if target_date > pd.to_datetime(start_date):
                target_date = target_date.strftime('%Y-%m-%d')
                valid_date = True
            else:
                print("Target date must be after start date.")
        except:
            print("Invalid date format. Please use YYYY-MM-DD.")
    
    notes = input("Notes (optional): ").strip()
    
    # Create the goal
    current_timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
    INSERT INTO goals 
    (name, type, target_amount, current_amount, start_date, target_date, 
     created_at, updated_at, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, goal_type, target_amount, current_amount, start_date, target_date, 
         current_timestamp, current_timestamp, notes))
    
    goal_id = cursor.lastrowid
    
    # If there's an initial amount, add it as first transaction
    if current_amount > 0:
        cursor.execute("""
        INSERT INTO goal_transactions
        (goal_id, amount, date, notes)
        VALUES (?, ?, ?, ?)
        """, (goal_id, current_amount, start_date, "Initial amount"))
    
    conn.commit()
    
    # Calculate time to goal
    days_to_goal = (pd.to_datetime(target_date) - pd.to_datetime(start_date)).days
    remaining = target_amount - current_amount
    
    # Calculate suggested contributions
    if days_to_goal > 0:
        daily = remaining / days_to_goal
        weekly = daily * 7
        monthly = daily * 30
        
        print(f"\nGoal '{name}' created successfully!")
        
        if remaining > 0:
            print(f"\nYou need to save ${remaining:.2f} in {days_to_goal} days")
            print(f"Suggested contributions to reach your goal:")
            print(f"  Daily: ${daily:.2f}")
            print(f"  Weekly: ${weekly:.2f}")
            print(f"  Monthly: ${monthly:.2f}")
    
    conn.close()


def show_goals(db_path: str) -> None:
    """
    Display all financial goals and their progress.
    
    Args:
        db_path: Path to the SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n=== Your Financial Goals ===")
    
    # Get all goals
    cursor.execute("""
    SELECT id, name, type, target_amount, current_amount, start_date, target_date, notes
    FROM goals
    ORDER BY target_date ASC
    """)
    
    goals = cursor.fetchall()
    
    if not goals:
        print("No goals found. Create one with --add-goal")
        conn.close()
        return
    
    for goal in goals:
        goal_id, name, goal_type, target, current, start_date, target_date, notes = goal
        
        # Calculate progress
        progress_pct = (current / target * 100) if target > 0 else 0
        remaining = target - current
        
        # Calculate days left and required contribution
        today = pd.Timestamp.now().strftime('%Y-%m-%d')
        days_passed = (pd.to_datetime(today) - pd.to_datetime(start_date)).days
        days_total = (pd.to_datetime(target_date) - pd.to_datetime(start_date)).days
        days_left = max(0, (pd.to_datetime(target_date) - pd.to_datetime(today)).days)
        
        # Get recent transactions
        cursor.execute("""
        SELECT date, amount
        FROM goal_transactions
        WHERE goal_id = ?
        ORDER BY date DESC
        LIMIT 3
        """, (goal_id,))
        
        recent_transactions = cursor.fetchall()
        
        print(f"\nGoal ID: {goal_id}")
        print(f"Name: {name} ({goal_type.replace('_', ' ').title()})")
        print(f"Progress: ${current:.2f} of ${target:.2f} ({progress_pct:.1f}%)")
        print(f"Remaining: ${remaining:.2f}")
        print(f"Timeline: {start_date} to {target_date} ({days_passed} days passed, {days_left} days left)")
        
        # Show daily/monthly needed to reach goal
        if days_left > 0 and remaining > 0:
            daily = remaining / days_left
            monthly = daily * 30
            print(f"To reach goal: ${daily:.2f}/day or ${monthly:.2f}/month")
        elif remaining <= 0:
            print("Goal achieved! 🎉")
        else:
            print("Past due date")
        
        # Show recent transactions if any
        if recent_transactions:
            print("Recent Activity:")
            for date, amount in recent_transactions:
                print(f"  {date}: ${amount:.2f}")
        
        if notes:
            print(f"Notes: {notes}")
        
        print("-" * 40)
    
    conn.close()


def update_goal_progress(db_path: str, goal_id: int) -> None:
    """
    Update progress on a specific goal.
    
    Args:
        db_path: Path to the SQLite database
        goal_id: ID of the goal to update
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if goal exists
    cursor.execute("""
    SELECT name, type, target_amount, current_amount, start_date, target_date
    FROM goals
    WHERE id = ?
    """, (goal_id,))
    
    goal = cursor.fetchone()
    if not goal:
        print(f"Goal with ID {goal_id} not found.")
        conn.close()
        return
    
    name, goal_type, target, current, start_date, target_date = goal
    
    print(f"\n=== Update Progress for Goal: {name} ===")
    print(f"Current progress: ${current:.2f} of ${target:.2f}")
    print(f"Remaining: ${target - current:.2f}")
    
    # Get contribution details
    valid_amount = False
    while not valid_amount:
        amount_str = input("Amount to add (or negative to subtract): $").strip()
        try:
            amount = float(amount_str)
            new_total = current + amount
            
            if new_total < 0:
                print("Total progress cannot be negative.")
            elif new_total > target and goal_type == 'savings':
                print(f"Warning: New amount (${new_total:.2f}) exceeds target (${target:.2f})")
                confirm = input("Continue anyway? (y/n): ").strip().lower()
                if confirm == 'y':
                    valid_amount = True
                else:
                    print("Update cancelled.")
            else:
                valid_amount = True
        except ValueError:
            print("Please enter a valid number.")
    
    # Get the date
    valid_date = False
    while not valid_date:
        date_str = input("Date (YYYY-MM-DD or today): ").strip()
        if date_str.lower() == 'today':
            date = pd.Timestamp.now().strftime('%Y-%m-%d')
            valid_date = True
        else:
            try:
                date = pd.to_datetime(date_str).strftime('%Y-%m-%d')
                valid_date = True
            except:
                print("Invalid date format. Please use YYYY-MM-DD.")
    
    notes = input("Notes (optional): ").strip()
    
    # Update goal progress
    cursor.execute("""
    UPDATE goals
    SET current_amount = current_amount + ?,
        updated_at = ?
    WHERE id = ?
    """, (amount, pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'), goal_id))
    
    # Add transaction record
    cursor.execute("""
    INSERT INTO goal_transactions
    (goal_id, amount, date, notes)
    VALUES (?, ?, ?, ?)
    """, (goal_id, amount, date, notes))
    
    conn.commit()
    
    # Show updated progress
    cursor.execute("""
    SELECT current_amount
    FROM goals
    WHERE id = ?
    """, (goal_id,))
    
    new_current = cursor.fetchone()[0]
    progress_pct = (new_current / target * 100) if target > 0 else 0
    remaining = target - new_current
    
    print(f"\nGoal updated successfully!")
    print(f"New progress: ${new_current:.2f} of ${target:.2f} ({progress_pct:.1f}%)")
    print(f"Remaining: ${remaining:.2f}")
    
    conn.close()


# ---------------------------
# Cash Flow Forecasting
# ---------------------------

def add_recurring_transaction(db_path: str) -> None:
    """
    Add a recurring transaction for cash flow forecasting.
    
    Args:
        db_path: Path to the SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n=== Add Recurring Transaction ===")
    
    # Get transaction details
    description = input("Description: ").strip()
    
    valid_amount = False
    while not valid_amount:
        try:
            amount = float(input("Amount: $").strip())
            if amount <= 0:
                print("Amount must be greater than zero.")
            else:
                valid_amount = True
        except ValueError:
            print("Please enter a valid number.")
    
    # Get transaction type
    tx_type = ''
    while tx_type not in ['income', 'expense']:
        tx_type = input("Type (income/expense): ").strip().lower()
    
    # If expense, make amount negative
    if tx_type == 'expense':
        amount = -abs(amount)
    
    # Get frequency
    frequency = ''
    valid_frequencies = ['daily', 'weekly', 'biweekly', 'monthly', 'quarterly', 'annual']
    while frequency not in valid_frequencies:
        frequency = input(f"Frequency ({'/'.join(valid_frequencies)}): ").strip().lower()
    
    # For monthly transactions, get day of month
    day_of_month = None
    if frequency == 'monthly':
        valid_day = False
        while not valid_day:
            try:
                day_of_month = int(input("Day of month (1-31): ").strip())
                if 1 <= day_of_month <= 31:
                    valid_day = True
                else:
                    print("Day must be between 1 and 31.")
            except ValueError:
                print("Please enter a valid number.")
    
    # For weekly transactions, get day of week
    day_of_week = None
    if frequency in ['weekly', 'biweekly']:
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        valid_day = False
        while not valid_day:
            day_input = input(f"Day of week ({', '.join(days)}): ").strip().lower()
            if day_input in days:
                day_of_week = days.index(day_input)
                valid_day = True
            else:
                print("Invalid day. Please enter a day name.")
    
    # Get start date
    valid_date = False
    while not valid_date:
        start_date_str = input("Start date (YYYY-MM-DD or today): ").strip()
        if start_date_str.lower() == 'today':
            start_date = pd.Timestamp.now().strftime('%Y-%m-%d')
            valid_date = True
        else:
            try:
                start_date = pd.to_datetime(start_date_str).strftime('%Y-%m-%d')
                valid_date = True
            except:
                print("Invalid date format. Please use YYYY-MM-DD.")
    
    # Get optional end date
    end_date = None
    end_date_str = input("End date (YYYY-MM-DD or leave empty for no end): ").strip()
    if end_date_str:
        try:
            end_date = pd.to_datetime(end_date_str).strftime('%Y-%m-%d')
            if pd.to_datetime(end_date) <= pd.to_datetime(start_date):
                print("Warning: End date is before or same as start date.")
                confirm = input("Continue anyway? (y/n): ").strip().lower()
                if confirm != 'y':
                    end_date = None
        except:
            print("Invalid date format. Ignoring end date.")
    
    # Get category from existing categories
    print("\nFetching categories from your transactions...")
    try:
        cursor.execute("""
        SELECT DISTINCT category 
        FROM consolidated_transactions 
        WHERE category IS NOT NULL AND category != ''
        LIMIT 10
        """)
        categories = [row[0] for row in cursor.fetchall()]
        if categories:
            print("Suggested categories:", ', '.join(categories))
    except sqlite3.Error:
        categories = []
    
    category = input("Category (optional): ").strip()
    
    notes = input("Notes (optional): ").strip()
    
    # Insert the recurring transaction
    current_timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
    INSERT INTO recurring_forecasts 
    (description, amount, type, frequency, day_of_month, day_of_week, 
     start_date, end_date, created_at, updated_at, category, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (description, amount, tx_type, frequency, day_of_month, day_of_week,
         start_date, end_date, current_timestamp, current_timestamp, category, notes))
    
    conn.commit()
    
    print(f"\nRecurring {tx_type} '{description}' added successfully!")
    
    # Show forecast preview
    print("\nForecast preview for the next 3 occurrences:")
    dates = calculate_recurring_dates(
        frequency, pd.to_datetime(start_date), 
        day_of_month, day_of_week, 3
    )
    
    for date in dates:
        print(f"  {date.strftime('%Y-%m-%d')}: ${abs(amount):.2f}")
    
    conn.close()


def calculate_recurring_dates(frequency: str, start_date: pd.Timestamp, 
                             day_of_month: Optional[int], 
                             day_of_week: Optional[int], 
                             count: int) -> List[pd.Timestamp]:
    """
    Calculate the next occurrence dates for a recurring transaction.
    
    Args:
        frequency: Type of recurrence ('daily', 'weekly', etc.)
        start_date: Starting date
        day_of_month: Day of month for monthly recurrences
        day_of_week: Day of week for weekly recurrences
        count: Number of occurrences to calculate
        
    Returns:
        List of dates
    """
    dates = []
    current_date = start_date
    
    if frequency == 'monthly' and day_of_month:
        # Start from the first occurrence
        if current_date.day <= day_of_month:
            # If start date is before the day of month, use current month
            current_date = pd.Timestamp(year=current_date.year, 
                                      month=current_date.month, 
                                      day=min(day_of_month, pd.Timestamp(year=current_date.year, 
                                                                        month=current_date.month, 
                                                                        day=1).days_in_month))
        else:
            # If start date is after the day of month, use next month
            next_month = current_date + pd.DateOffset(months=1)
            current_date = pd.Timestamp(year=next_month.year, 
                                      month=next_month.month, 
                                      day=min(day_of_month, pd.Timestamp(year=next_month.year, 
                                                                        month=next_month.month, 
                                                                        day=1).days_in_month))
    
    elif frequency in ['weekly', 'biweekly'] and day_of_week is not None:
        # Start from the first occurrence
        days_ahead = day_of_week - current_date.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        current_date = current_date + pd.DateOffset(days=days_ahead)
    
    # Calculate occurrences
    while len(dates) < count:
        if current_date >= start_date:
            dates.append(current_date)
        
        # Calculate next date based on frequency
        if frequency == 'daily':
            current_date = current_date + pd.DateOffset(days=1)
        elif frequency == 'weekly':
            current_date = current_date + pd.DateOffset(weeks=1)
        elif frequency == 'biweekly':
            current_date = current_date + pd.DateOffset(weeks=2)
        elif frequency == 'monthly':
            next_month = current_date + pd.DateOffset(months=1)
            current_date = pd.Timestamp(
                year=next_month.year, 
                month=next_month.month, 
                day=min(day_of_month or current_date.day, 
                        pd.Timestamp(year=next_month.year, month=next_month.month, day=1).days_in_month)
            )
        elif frequency == 'quarterly':
            current_date = current_date + pd.DateOffset(months=3)
        elif frequency == 'annual':
            current_date = current_date + pd.DateOffset(years=1)
    
    return dates


def show_cash_flow_forecast(db_path: str, months: int = 3) -> None:
    """
    Show a cash flow forecast based on recurring transactions.
    
    Args:
        db_path: Path to the SQLite database
        months: Number of months to forecast
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all recurring transactions
    cursor.execute("""
    SELECT id, description, amount, type, frequency, day_of_month, day_of_week,
           start_date, end_date, category, notes
    FROM recurring_forecasts
    ORDER BY amount DESC  -- Income first (assuming positive values)
    """)
    
    recurring_items = cursor.fetchall()
    
    if not recurring_items:
        print("\nNo recurring transactions found. Add some with --add-recurring")
        conn.close()
        return
    
    print(f"\n=== Cash Flow Forecast ({months} Months) ===")
    
    # Calculate forecast dates
    today = pd.Timestamp.now()
    end_date = today + pd.DateOffset(months=months)
    
    # Store forecast by date
    forecast = {}
    
    # Process each recurring transaction
    for item in recurring_items:
        (item_id, description, amount, tx_type, frequency, 
         day_of_month, day_of_week, start_date, end_date_str, category, notes) = item
        
        # Skip if end date is in the past
        if end_date_str and pd.to_datetime(end_date_str) < today:
            continue
        
        # Calculate occurrences
        start = max(pd.to_datetime(start_date), today)
        dates = calculate_recurring_dates(
            frequency, start, day_of_month, day_of_week, 100  # Get plenty of dates
        )
        
        # Filter dates within forecast period
        for date in dates:
            if date > end_date:
                break
                
            # Skip if past end_date for this item
            if end_date_str and date > pd.to_datetime(end_date_str):
                continue
                
            # Add to forecast
            month_key = f"{date.year}-{date.month:02d}"
            if month_key not in forecast:
                forecast[month_key] = {
                    'items': [],
                    'income': 0,
                    'expenses': 0,
                    'net': 0
                }
            
            forecast[month_key]['items'].append({
                'date': date.strftime('%Y-%m-%d'),
                'description': description,
                'amount': amount,
                'type': tx_type,
                'category': category
            })
            
            # Update totals
            if amount > 0:
                forecast[month_key]['income'] += amount
            else:
                forecast[month_key]['expenses'] += abs(amount)
            forecast[month_key]['net'] += amount
    
    # Show forecast summary by month
    if not forecast:
        print("No recurring transactions in the forecast period.")
        conn.close()
        return
    
    # Sort months
    sorted_months = sorted(forecast.keys())
    
    overall_income = 0
    overall_expenses = 0
    overall_net = 0
    
    print("\nMonthly Summary:")
    print(f"{'Month':<10} {'Income':<12} {'Expenses':<12} {'Net Cash Flow':<15} {'Balance':<12}")
    print("-" * 60)
    
    cumulative_balance = 0
    
    for month in sorted_months:
        f = forecast[month]
        month_name = pd.Timestamp(year=int(month.split('-')[0]), month=int(month.split('-')[1]), day=1).strftime('%b %Y')
        
        income = f['income']
        expenses = f['expenses']
        net = f['net']
        
        overall_income += income
        overall_expenses += expenses
        overall_net += net
        
        cumulative_balance += net
        
        # Format display
        print(f"{month_name:<10} ${income:<10.2f} ${expenses:<10.2f} ${net:<13.2f} ${cumulative_balance:<10.2f}")
    
    print("-" * 60)
    print(f"{'Total':<10} ${overall_income:<10.2f} ${overall_expenses:<10.2f} ${overall_net:<13.2f}")
    
    # Show detailed transactions for closest month
    closest_month = sorted_months[0]
    month_name = pd.Timestamp(year=int(closest_month.split('-')[0]), 
                             month=int(closest_month.split('-')[1]), 
                             day=1).strftime('%B %Y')
    
    print(f"\nDetailed Forecast for {month_name}:")
    print(f"{'Date':<12} {'Description':<30} {'Amount':<10} {'Type':<8}")
    print("-" * 70)
    
    # Sort by date
    sorted_items = sorted(forecast[closest_month]['items'], key=lambda x: x['date'])
    
    for item in sorted_items:
        print(f"{item['date']:<12} {item['description'][:28]:<30} ${abs(item['amount']):<8.2f} {item['type']:<8}")
    
    # Suggest improvements
    print("\nInsights:")
    if overall_net < 0:
        print("⚠️ Forecasted expenses exceed income. Consider reviewing discretionary spending.")
    
    expense_months = sum(1 for m in sorted_months if forecast[m]['net'] < 0)
    if expense_months > 0:
        print(f"⚠️ {expense_months} out of {len(sorted_months)} months show negative cash flow.")
    
    if overall_net > 0:
        print(f"💰 Projected savings over {months} months: ${overall_net:.2f}")
        
        # Suggest goal allocation
        cursor.execute("""
        SELECT id, name, target_amount, current_amount
        FROM goals
        WHERE current_amount < target_amount
        ORDER BY (target_amount - current_amount) ASC
        LIMIT 1
        """)
        
        goal = cursor.fetchone()
        if goal:
            goal_id, goal_name, target, current = goal
            remaining = target - current
            
            if overall_net >= remaining:
                print(f"💡 You could fully fund your '{goal_name}' goal (${remaining:.2f} needed)")
            else:
                coverage = overall_net / remaining * 100
                print(f"💡 You could fund {coverage:.1f}% of your '{goal_name}' goal")
    
    conn.close()

# ---------------------------
# Smart Categorization with AI
# ---------------------------

def train_category_classifier(db_path: str, model_dir: str) -> Optional[Pipeline]:
    """
    Train a machine learning model to automatically categorize transactions.
    
    Args:
        db_path: Path to the SQLite database
        model_dir: Directory to save the trained model
        
    Returns:
        Trained classification model
    """
    # Create model dir if it doesn't exist
    os.makedirs(model_dir, exist_ok=True)
    
    # Make sure database directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if consolidated_transactions table exists
    cursor.execute("""
    SELECT count(name) FROM sqlite_master 
    WHERE type='table' AND name='consolidated_transactions'
    """)
    
    if cursor.fetchone()[0] == 0:
        print("Error: The consolidated_transactions table doesn't exist yet.")
        print("Please run with --consolidate flag first to create and populate the table.")
        print("Example: python src/app.py --consolidate")
        conn.close()
        return None
    
    # Get all categorized transactions for training
    query = """
    SELECT description, amount, source, category 
    FROM consolidated_transactions
    WHERE category IS NOT NULL AND category != ''
    """
    
    try:
        df = pd.read_sql_query(query, conn)
        conn.close()
    except (sqlite3.OperationalError, pd.errors.DatabaseError) as e:
        print(f"Database error: {e}")
        print("Please make sure you've imported transactions and consolidated them first.")
        print("Run: python src/app.py --consolidate")
        conn.close()
        return None
    
    if df.empty or len(df) < 20:  # Need a reasonable amount of data
        print("Not enough categorized transactions to train a model.")
        print("Please categorize more transactions and try again.")
        return None
    
    # Count categories to see if we have enough data
    category_counts = df['category'].value_counts()
    valid_categories = category_counts[category_counts >= 5].index.tolist()
    
    if len(valid_categories) < 3:  # Need at least a few categories
        print(f"Need more diverse categories. Only found {len(valid_categories)} with 5+ examples.")
        print("Please add more varied transactions and try again.")
        return None
    
    # Filter to only include categories with enough examples
    df = df[df['category'].isin(valid_categories)]
    
    print(f"Training with {len(df)} transactions across {len(valid_categories)} categories.")
    print(f"Top categories: {', '.join(category_counts.index[:5])}")
    
    # Convert amount to numeric and handle any non-numeric values
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    df['amount'] = df['amount'].fillna(0)
    
    # Ensure description is a string and handle null values
    df['description'] = df['description'].fillna('').astype(str)
    
    # Prepare features: combine description with other features
    df['amount_str'] = df['amount'].apply(lambda x: 'high' if abs(x) > 100 else 'medium' if abs(x) > 20 else 'low')
    df['text_features'] = df['description'] + ' ' + df['amount_str']
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        df['text_features'], 
        df['category'],
        test_size=0.25, 
        random_state=42
    )
    
    # Create a pipeline with TF-IDF and RandomForest
    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(
            min_df=2,
            max_df=0.8,
            ngram_range=(1, 2),
            stop_words='english'
        )),
        ('classifier', RandomForestClassifier(
            n_estimators=100,
            class_weight='balanced',
            random_state=42
        ))
    ])
    
    # Train the model
    print("Training category classifier...")
    pipeline.fit(X_train, y_train)
    
    # Evaluate
    y_pred = pipeline.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    
    print(f"Model accuracy: {accuracy:.2f}")
    
    # Show classification report with main metrics
    report = classification_report(y_test, y_pred)
    print("\nClassification Report:")
    print(report)
    
    # Save the model
    model_path = os.path.join(model_dir, f"category_classifier_{datetime.datetime.now().strftime('%Y%m%d')}.joblib")
    joblib.dump(pipeline, model_path)
    print(f"Model saved to: {model_path}")
    
    # Also save as latest model
    latest_model_path = os.path.join(model_dir, "latest_category_classifier.joblib")
    joblib.dump(pipeline, latest_model_path)
    
    # Save the valid categories for reference
    with open(os.path.join(model_dir, "valid_categories.txt"), "w") as f:
        f.write("\n".join(valid_categories))
    
    return pipeline


def get_latest_category_model(model_dir: str) -> Optional[Pipeline]:
    """
    Get the most recently trained category classifier model.
    
    Args:
        model_dir: Directory where models are stored
        
    Returns:
        Most recent trained model or None if no model exists
    """
    latest_model_path = os.path.join(model_dir, "latest_category_classifier.joblib")
    if os.path.exists(latest_model_path):
        return joblib.load(latest_model_path)
    return None


def get_valid_categories(model_dir: str) -> List[str]:
    """
    Get the list of valid categories for the trained model.
    
    Args:
        model_dir: Directory where models are stored
        
    Returns:
        List of valid categories
    """
    categories_path = os.path.join(model_dir, "valid_categories.txt")
    if os.path.exists(categories_path):
        with open(categories_path, "r") as f:
            return [line.strip() for line in f.readlines()]
    return []


def categorize_transactions(db_path: str, model_dir: str, limit: int = 100) -> None:
    """
    Automatically categorize uncategorized transactions using
    machine learning model.
    
    Args:
        db_path: Path to the SQLite database
        model_dir: Directory where models are stored
        limit: Maximum number of transactions to process
    """
    # Load the model
    model = get_latest_category_model(model_dir)
    if model is None:
        print("No category classification model found.")
        print("Please train a model first with --train-category-model")
        return
    
    # Get valid categories
    valid_categories = get_valid_categories(model_dir)
    if not valid_categories:
        print("No valid categories found for the model.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if consolidated_transactions table exists
    cursor.execute("""
    SELECT count(name) FROM sqlite_master 
    WHERE type='table' AND name='consolidated_transactions'
    """)
    
    if cursor.fetchone()[0] == 0:
        print("Error: The consolidated_transactions table doesn't exist yet.")
        print("Please run with --consolidate flag first to create and populate the table.")
        print("Example: python src/app.py --consolidate")
        conn.close()
        return
    
    # Get uncategorized transactions
    try:
        query = f"""
        SELECT id, description, amount, source, date_posted 
        FROM consolidated_transactions
        WHERE (category IS NULL OR category = '')
        ORDER BY date_posted DESC
        LIMIT {limit}
        """
        
        df = pd.read_sql_query(query, conn)
    except (sqlite3.OperationalError, pd.errors.DatabaseError) as e:
        print(f"Database error: {e}")
        print("Please make sure you've imported transactions and consolidated them first.")
        print("Run: python src/app.py --consolidate")
        conn.close()
        return
    
    if df.empty:
        print("No uncategorized transactions found.")
        conn.close()
        return
    
    print(f"Found {len(df)} uncategorized transactions to process.")
    
    # Convert amount to numeric and handle any non-numeric values
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    df['amount'] = df['amount'].fillna(0)
    
    # Ensure description is a string and handle null values
    df['description'] = df['description'].fillna('').astype(str)
    
    # Prepare features for prediction
    df['amount_str'] = df['amount'].apply(lambda x: 'high' if abs(x) > 100 else 'medium' if abs(x) > 20 else 'low')
    df['text_features'] = df['description'] + ' ' + df['amount_str']
    
    # Make predictions
    print("Suggesting categories...")
    
    predictions = model.predict(df['text_features'])
    probabilities = model.predict_proba(df['text_features'])
    df['predicted_category'] = predictions
    df['confidence'] = [max(prob) for prob in probabilities]
    
    # Show predictions
    print("\nCategory Suggestions:")
    print(f"{'ID':<5} {'Description':<40} {'Amount':<10} {'Suggested Category':<20} {'Confidence':<10}")
    print("-" * 90)
    
    # Sort by confidence
    df_sorted = df.sort_values('confidence', ascending=False)
    
    # Show top suggestions
    for i, row in df_sorted.head(10).iterrows():
        desc = (row['description'][:37] + "...") if len(row['description']) > 40 else row['description']
        print(f"{row['id']:<5} {desc:<40} ${row['amount']:<8.2f} {row['predicted_category']:<20} {row['confidence']:.2f}")
    
    # Ask if we should apply predictions
    apply_mode = input("\nApply predictions? (a=all, h=high confidence only, i=interactive, n=none): ").strip().lower()
    
    if apply_mode in ['a', 'h', 'i']:
        cursor = conn.cursor()
        count = 0
        
        # Set confidence threshold
        confidence_threshold = 0.7 if apply_mode == 'h' else 0.0
        
        # Process each prediction
        for i, row in df_sorted.iterrows():
            # Skip low confidence predictions for 'high confidence' mode
            if apply_mode == 'h' and row['confidence'] < confidence_threshold:
                continue
                
            # For interactive mode, ask for each prediction
            if apply_mode == 'i':
                print(f"\nTransaction: {row['description']}")
                print(f"Amount: ${row['amount']:.2f}, Date: {row['date_posted']}")
                print(f"Suggested category: {row['predicted_category']} (confidence: {row['confidence']:.2f})")
                
                # Show prediction alternatives (top 3)
                category_probs = [(model.classes_[j], prob) for j, prob in enumerate(probabilities[i])]
                category_probs.sort(key=lambda x: x[1], reverse=True)
                
                print("Alternative categories:")
                for j, (cat, prob) in enumerate(category_probs[:3]):
                    print(f"{j+1}. {cat} ({prob:.2f})")
                
                choice = input("Accept suggestion? (y/n/1-3 for alternative/s to skip): ").strip().lower()
                
                if choice == 'y':
                    category = row['predicted_category']
                elif choice.isdigit() and 1 <= int(choice) <= 3:
                    category = category_probs[int(choice)-1][0]
                elif choice == 'n':
                    # Let user enter a custom category
                    print("Available categories:")
                    for j, cat in enumerate(valid_categories[:10]):
                        print(f"{j+1}. {cat}")
                    print("c. Custom category")
                    
                    cat_choice = input("Enter category choice (1-10 or c): ").strip().lower()
                    if cat_choice == 'c':
                        category = input("Enter custom category: ").strip()
                    elif cat_choice.isdigit() and 1 <= int(cat_choice) <= len(valid_categories[:10]):
                        category = valid_categories[int(cat_choice)-1]
                    else:
                        print("Invalid choice, skipping.")
                        continue
                else:
                    # Skip this transaction
                    continue
            else:
                # For automatic modes (all or high confidence)
                category = row['predicted_category']
            
            # Update the category
            cursor.execute("""
            UPDATE consolidated_transactions
            SET category = ?
            WHERE id = ?
            """, (category, row['id']))
            
            count += 1
        
        conn.commit()
        print(f"\nApplied categories to {count} transactions.")
    else:
        print("No categories applied.")
    
    conn.close()


def suggest_category_for_transaction(description: str, amount: float, model_dir: str) -> Optional[str]:
    """
    Suggest a category for a given transaction based on its description and amount.
    
    Args:
        description: Transaction description text
        amount: Transaction amount
        model_dir: Directory where models are stored
        
    Returns:
        Suggested category or None if no model available
    """
    # Load the model
    model = get_latest_category_model(model_dir)
    if model is None:
        return None
    
    # Ensure amount is numeric
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        amount = 0
    
    # Ensure description is a string
    if description is None:
        description = ''
    else:
        description = str(description)
        
    # Prepare the features
    amount_str = 'high' if abs(amount) > 100 else 'medium' if abs(amount) > 20 else 'low'
    text_features = description + ' ' + amount_str
    
    # Make prediction
    prediction = model.predict([text_features])[0]
    probabilities = model.predict_proba([text_features])[0]
    confidence = max(probabilities)
    
    # Get top alternatives
    category_probs = [(model.classes_[i], prob) for i, prob in enumerate(probabilities)]
    category_probs.sort(key=lambda x: x[1], reverse=True)
    
    # Return the suggested category along with confidence and alternatives
    return {
        'category': prediction,
        'confidence': confidence,
        'alternatives': category_probs[:3]
    }


def analyze_spending_patterns(db_path: str) -> None:
    """
    Analyze spending patterns to provide insights and recommendations.
    
    Args:
        db_path: Path to the SQLite database
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("\n=== Spending Pattern Analysis ===")
    
    # Check if consolidated_transactions table exists
    cursor.execute("""
    SELECT count(name) FROM sqlite_master 
    WHERE type='table' AND name='consolidated_transactions'
    """)
    
    if cursor.fetchone()[0] == 0:
        print("Error: The consolidated_transactions table doesn't exist yet.")
        print("Please run with --consolidate flag first to create and populate the table.")
        print("Example: python src/app.py --consolidate")
        conn.close()
        return
        
    # Get the date range of transactions
    try:
        cursor.execute("""
        SELECT MIN(date_posted), MAX(date_posted)
        FROM consolidated_transactions
        """)
        
        date_range = cursor.fetchone()
        if not date_range or not date_range[0] or not date_range[1]:
            print("No transaction data available for analysis.")
            conn.close()
            return
        
        min_date, max_date = date_range
        print(f"Analyzing transactions from {min_date} to {max_date}")
    except sqlite3.OperationalError as e:
        print(f"Error reading from database: {e}")
        print("Please make sure you've imported transactions and consolidated them first.")
        print("Run: python src/app.py --consolidate")
        conn.close()
        return
    
    # Get spending by category for the last 3 months
    three_months_ago = (pd.to_datetime(max_date) - pd.DateOffset(months=3)).strftime('%Y-%m-%d')
    
    try:
        df_category = pd.read_sql_query("""
        SELECT category, SUM(amount) as total_spent
        FROM consolidated_transactions
        WHERE category IS NOT NULL 
        AND category != ''
        AND date_posted >= ?
        AND amount < 0  -- Only expenses (negative amounts)
        GROUP BY category
        ORDER BY total_spent ASC  -- Ascending because expenses are negative
        LIMIT 10
        """, conn, params=(three_months_ago,))
        
        # Get spending by month
        df_monthly = pd.read_sql_query("""
        SELECT 
            strftime('%Y-%m', date_posted) as month,
            SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as expenses,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income
        FROM consolidated_transactions
        GROUP BY strftime('%Y-%m', date_posted)
        ORDER BY month DESC
        LIMIT 6
        """, conn)
        
        # Get recurring expenses
        df_recurring = pd.read_sql_query("""
        SELECT description, category, AVG(amount) as avg_amount, COUNT(*) as occurrence_count
        FROM consolidated_transactions
        WHERE amount < 0
        AND date_posted >= ?
        GROUP BY description, category
        HAVING COUNT(*) >= 3
        ORDER BY avg_amount ASC
        LIMIT 10
        """, conn, params=(three_months_ago,))
    except (sqlite3.OperationalError, pd.errors.DatabaseError) as e:
        print(f"Error analyzing transactions: {e}")
        print("There may be a problem with the database structure or data.")
        conn.close()
        return
    
    conn.close()
    
    # Display insights
    
    # Top spending categories
    if not df_category.empty:
        print("\n🔍 Top spending categories (last 3 months):")
        for i, row in df_category.iterrows():
            print(f"  {row['category']:<20} ${abs(row['total_spent']):.2f}")
    
    # Monthly spending trends
    if not df_monthly.empty:
        print("\n📊 Monthly spending trends:")
        print(f"{'Month':<10} {'Income':<12} {'Expenses':<12} {'Net':<12}")
        print("-" * 50)
        
        for i, row in df_monthly.iterrows():
            month = row['month']
            income = row['income']
            expenses = abs(row['expenses'])
            net = income + row['expenses']  # expenses are negative
            
            print(f"{month:<10} ${income:<10.2f} ${expenses:<10.2f} ${net:<10.2f}")
    
    # Recurring expenses
    if not df_recurring.empty:
        print("\n🔄 Recurring expenses:")
        for i, row in df_recurring.iterrows():
            desc = (row['description'][:30] + "...") if len(row['description']) > 33 else row['description']
            category = row['category'] if row['category'] else 'Uncategorized'
            print(f"  {desc:<33} ${abs(row['avg_amount']):.2f}/month ({category})")
    
    # Provide recommendations
    print("\n💡 Recommendations:")
    
    # Recommend budget adjustments based on spending patterns
    if not df_category.empty:
        max_category = df_category.iloc[0]
        print(f"• Your highest spending category is {max_category['category']} (${abs(max_category['total_spent']):.2f}).")
        print(f"  Consider setting a budget limit for this category.")
    
    # Identify potential savings from recurring expenses
    if not df_recurring.empty and len(df_recurring) > 3:
        recurring_total = abs(df_recurring['avg_amount'].sum())
        print(f"• You have {len(df_recurring)} recurring expenses totaling ~${recurring_total:.2f}/month.")
        print(f"  Reviewing these subscriptions could yield potential savings.")
    
    # Check income vs expenses trend
    if not df_monthly.empty and len(df_monthly) >= 3:
        recent_months = df_monthly.head(3)
        avg_net = (recent_months['income'] + recent_months['expenses']).mean()
        
        if avg_net < 0:
            print(f"• Warning: Your average monthly spending exceeds income by ${abs(avg_net):.2f}.")
            print(f"  Consider reducing expenses or finding additional income sources.")
        elif avg_net > 0:
            print(f"• Good job! You're saving an average of ${avg_net:.2f} per month.")
            print(f"  Consider allocating this to your savings goals.")

# ---------------------------
# Machine Learning and Classification
# ---------------------------

def get_classifier_dataset(db_path: str) -> Tuple[Optional[pd.Series], Optional[pd.Series]]:
    """
    Extract dataset for training the rental expense classifier.
    
    Args:
        db_path: Path to the SQLite database
        
    Returns:
        X: List of transaction descriptions
        y: List of labels (1 for rental, 0 for non-rental)
    """
    conn = sqlite3.connect(db_path)
    
    # Get all classified transactions
    query = """
    SELECT description, category, source, amount, rental_related
    FROM consolidated_transactions
    WHERE rental_related IS NOT NULL
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if df.empty:
        print("No classified transactions found. Please classify some transactions first.")
        return None, None
    
    # Prepare features and target
    X = df['description'].fillna('').astype(str)
    y = df['rental_related'].astype(int)
    
    print(f"Dataset prepared: {len(X)} transactions ({sum(y)} rental, {len(y) - sum(y)} non-rental)")
    
    return X, y


def train_rental_classifier(db_path: str, model_dir: str) -> Optional[Pipeline]:
    """
    Train a machine learning model to classify transactions as rental-related.
    
    Args:
        db_path: Path to the SQLite database
        model_dir: Directory to save the trained model
    
    Returns:
        The trained model and accuracy metrics
    """
    # Create model dir if it doesn't exist
    os.makedirs(model_dir, exist_ok=True)
    
    # Get training data
    X, y = get_classifier_dataset(db_path)
    if X is None or len(X) < 10:
        print("Not enough data to train a model. Please classify more transactions.")
        return None
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)
    
    # Create a pipeline with TF-IDF and RandomForest
    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(
            min_df=2, max_df=0.8, 
            ngram_range=(1, 2),  # Use unigrams and bigrams
            stop_words='english'
        )),
        ('classifier', RandomForestClassifier(
            n_estimators=100,
            class_weight='balanced',
            random_state=42
        ))
    ])
    
    # Train model
    print("Training rental expense classifier...")
    pipeline.fit(X_train, y_train)
    
    # Evaluate
    y_pred = pipeline.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred)
    
    print(f"Model accuracy: {accuracy:.2f}")
    print("\nClassification Report:")
    print(report)
    
    # Save model
    model_path = os.path.join(model_dir, f"rental_classifier_{datetime.datetime.now().strftime('%Y%m%d')}.joblib")
    joblib.dump(pipeline, model_path)
    print(f"Model saved to: {model_path}")
    
    # Also save as latest model
    latest_model_path = os.path.join(model_dir, "latest_rental_classifier.joblib")
    joblib.dump(pipeline, latest_model_path)
    
    return pipeline


def get_latest_model(model_dir: str) -> Optional[Pipeline]:
    """
    Get the most recently trained model.
    
    Args:
        model_dir: Directory where models are stored
        
    Returns:
        Most recent trained model
    """
    latest_model_path = os.path.join(model_dir, "latest_rental_classifier.joblib")
    if os.path.exists(latest_model_path):
        return joblib.load(latest_model_path)
    return None


def batch_predict_rentals(db_path: str, model_dir: str, limit: int = 100) -> None:
    """
    Use ML model to predict rental classification for unclassified transactions.
    
    Args:
        db_path: Path to the SQLite database
        model_dir: Directory where models are stored
        limit: Maximum number of transactions to process
    """
    # Load the model
    model = get_latest_model(model_dir)
    if model is None:
        print("No trained model found. Please train a model first.")
        return
    
    conn = sqlite3.connect(db_path)
    
    # Get unclassified transactions
    query = f"""
    SELECT id, description, category, source, amount
    FROM consolidated_transactions
    WHERE rental_related IS NULL
    LIMIT {limit}
    """
    
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        print("No unclassified transactions found.")
        conn.close()
        return
    
    # Make predictions
    print(f"Making predictions for {len(df)} transactions...")
    predictions = model.predict(df['description'].fillna('').astype(str))
    probabilities = model.predict_proba(df['description'].fillna('').astype(str))
    
    # Add predictions to dataframe
    df['rental_predicted'] = predictions
    df['confidence'] = [max(prob) for prob in probabilities]
    
    # Show predictions
    print("\nPredictions (showing top 10 with highest confidence):")
    print(f"{'ID':<5} {'Confidence':<10} {'Rental':<6} {'Description':<50}")
    print("-" * 80)
    
    # Sort by confidence
    df_sorted = df.sort_values('confidence', ascending=False)
    
    for i, row in df_sorted.head(10).iterrows():
        rental = "Yes" if row['rental_predicted'] == 1 else "No"
        desc = row['description'][:47] + "..." if len(row['description']) > 50 else row['description']
        print(f"{row['id']:<5} {row['confidence']:.2f}      {rental:<6} {desc:<50}")
    
    # Ask if we should apply predictions
    apply = input("\nApply predictions to database? (y/n): ").strip().lower()
    if apply == 'y':
        cursor = conn.cursor()
        count = 0
        
        # Only apply high-confidence predictions
        confidence_threshold = 0.7
        
        for i, row in df_sorted.iterrows():
            if row['confidence'] >= confidence_threshold:
                cursor.execute("""
                    UPDATE consolidated_transactions
                    SET rental_related = ?
                    WHERE id = ?
                """, (int(row['rental_predicted']), row['id']))
                count += 1
        
        conn.commit()
        print(f"\nApplied {count} high-confidence predictions (threshold: {confidence_threshold})")
    
    conn.close()


# ---------------------------
# Main Entry Point
# ---------------------------

def main():
    """Main entry point for the application."""
    # Make sure necessary directories exist
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Budgeting App - Transaction Import Tool')
    parser.add_argument('--init', action='store_true',
                        help='Initialize the database with required tables')
    parser.add_argument('--full', action='store_true', 
                        help='Perform a full import (override incremental)')
    parser.add_argument('--interactive', action='store_true',
                        help='Interactive mode: name sources and map columns manually')
    parser.add_argument('--history', action='store_true',
                        help='Show import history')
    parser.add_argument('--consolidate', action='store_true', 
                        help='Consolidate transactions from all sources')
    
    # Classification arguments
    parser.add_argument('--classify', action='store_true',
                        help='Run interactive classification')
    parser.add_argument('--mode', choices=['all', 'rental', 'recurring', 'subscription', 'tax', 'equipment'],
                        default='all', help='Classification mode')
    parser.add_argument('--sample-size', type=int, default=5,
                        help='Number of transactions to classify per batch')
    parser.add_argument('--detect-recurring', action='store_true',
                        help='Auto-detect recurring transactions')
    parser.add_argument('--summary', action='store_true',
                        help='Show transaction summary')
    
    # ML model arguments
    parser.add_argument('--train-model', action='store_true',
                        help='Train a machine learning model for rental classification')
    parser.add_argument('--predict', action='store_true',
                        help='Use ML model to predict rental classifications')
    parser.add_argument('--predict-limit', type=int, default=100,
                        help='Number of transactions to predict (default: 100)')
    
    # Smart Categorization arguments
    parser.add_argument('--train-category-model', action='store_true',
                        help='Train a smart categorization model for transactions')
    parser.add_argument('--auto-categorize', action='store_true',
                        help='Automatically categorize transactions using AI')
    parser.add_argument('--categorize-limit', type=int, default=100,
                        help='Number of transactions to categorize (default: 100)')
    parser.add_argument('--analyze-spending', action='store_true',
                        help='Analyze spending patterns and provide insights')
    
    # Budget management arguments
    parser.add_argument('--budget', action='store_true',
                        help='Launch budget management interface')
    parser.add_argument('--create-budget', action='store_true',
                        help='Create a new budget')
    parser.add_argument('--compare-budget', type=int, metavar='BUDGET_ID',
                        help='Compare actual spending with specified budget')
                        
    # Goals management
    parser.add_argument('--goals', action='store_true',
                        help='Show financial goals')
    parser.add_argument('--add-goal', action='store_true',
                        help='Add a new financial goal')
    parser.add_argument('--update-goal', type=int, metavar='GOAL_ID',
                        help='Update progress on a specific goal')
    
    # Cash flow forecasting
    parser.add_argument('--forecast', action='store_true',
                        help='Show cash flow forecast')
    parser.add_argument('--add-recurring', action='store_true',
                        help='Add a recurring transaction for cash flow forecasting')
    parser.add_argument('--forecast-months', type=int, default=3,
                        help='Number of months to forecast (default: 3)')
                        
    args = parser.parse_args()
    
    # Show import history if requested
    if args.history:
        list_import_history(DB_PATH)
    
    # Show transaction summary if requested
    if args.summary:
        show_transaction_summary(DB_PATH)
    
    # Initialize database if requested
    if args.init:
        # Create database connection with all required tables
        conn = initialize_database(DB_PATH)
        if conn:
            print("Database initialized successfully with all required tables.")
            conn.close()
        else:
            print("Error initializing database.")
        
    # Run the import with incremental flag based on args
    if not (args.init or args.history or args.summary or args.train_model or args.predict or 
            args.detect_recurring or args.budget or args.create_budget or 
            args.compare_budget or args.goals or args.add_goal or args.update_goal or 
            args.forecast or args.add_recurring or args.train_category_model or 
            args.auto_categorize or args.analyze_spending) or args.full or args.consolidate or args.classify:
        ingest_csv_to_db(CSV_DIR, DB_PATH, 
                          incremental=not args.full,
                          interactive=args.interactive)
        
    # Consolidate if requested
    if args.consolidate:
        consolidate_transactions(DB_PATH)
        add_classification_columns(DB_PATH)
    
    # Auto-detect recurring transactions if requested
    if args.detect_recurring:
        detect_recurring_transactions(DB_PATH)
    
    # Run classification if requested
    if args.classify:
        interactive_classification(DB_PATH, sample_size=args.sample_size, mode=args.mode)
        
    # Train rental ML model if requested
    if args.train_model:
        train_rental_classifier(DB_PATH, MODEL_DIR)
        
    # Use ML model to predict classifications
    if args.predict:
        batch_predict_rentals(DB_PATH, MODEL_DIR, limit=args.predict_limit)
    
    # Smart categorization with AI
    if args.train_category_model:
        train_category_classifier(DB_PATH, MODEL_DIR)
    if args.auto_categorize:
        categorize_transactions(DB_PATH, MODEL_DIR, limit=args.categorize_limit)
    if args.analyze_spending:
        analyze_spending_patterns(DB_PATH)
    
    # Budget management
    if args.budget:
        show_budgets(DB_PATH)
    if args.create_budget:
        create_budget(DB_PATH)
    if args.compare_budget:
        compare_budget_vs_actual(DB_PATH, args.compare_budget)
    
    # Goals management
    if args.goals:
        show_goals(DB_PATH)
    if args.add_goal:
        add_goal(DB_PATH)
    if args.update_goal:
        update_goal_progress(DB_PATH, args.update_goal)
    
    # Cash flow forecasting
    if args.forecast:
        show_cash_flow_forecast(DB_PATH, args.forecast_months)
    if args.add_recurring:
        add_recurring_transaction(DB_PATH)


if __name__ == "__main__":
    main()
