import pandas as pd
import os
import sqlite3
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score
from sklearn.pipeline import Pipeline
import joblib
import datetime

# Building the Web App for my budgeting application
base_dir = '/Users/jag/workspace/github.com/jessiegibson/budgeting-app'
csv_dir = f'{base_dir}/data/'
db_path = f"{base_dir}/db/transactions.db"
model_dir = f"{base_dir}/models"

account_names = {}

def clean_column_name(df):
    df.columns = df.columns.str.replace(' ','_').str.lower()
    df.columns = [re.sub(r'\W+','_',col.strip()) for col in df.columns]
    return df

def find_source_in_filename(filename):
    """
    Identify the source financial institution from the CSV filename.
    Uses filename pattern matching to categorize the data source.
    """
    filename = filename.lower()
    print(f"Processing filename: {filename}")
    
    # Use more specific checks to avoid false matches
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


def clean_transaction_data(df):
    df.fillna({'Amount': 0}, inplace=True)


def create_import_log_table(conn):
    """Create a table to track transaction import history if it doesn't exist"""
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

def get_last_import_date(conn, source):
    """Get the most recent import date for a given source"""
    cursor = conn.cursor()
    cursor.execute("""
    SELECT last_import_date FROM import_log 
    WHERE source = ? 
    ORDER BY import_timestamp DESC LIMIT 1
    """, (source,))
    result = cursor.fetchone()
    return result[0] if result else None

def log_import(conn, source, filename, last_date, num_transactions):
    """Log an import operation to the database"""
    cursor = conn.cursor()
    import_timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
    INSERT INTO import_log 
    (source, filename, last_import_date, import_timestamp, num_transactions)
    VALUES (?, ?, ?, ?, ?)
    """, (source, filename, last_date, import_timestamp, num_transactions))
    conn.commit()

def get_date_column_for_source(source):
    """Return the correct date column name for each data source"""
    date_columns = {
        'chase': 'date_posted',
        'discover': 'date_posted',  # or 'date_trans' depending on preference
        'amex_plat': 'date_posted',
        'amex_rose': 'date_posted',
        'home_depot': 'date'
    }
    return date_columns.get(source)

def prompt_for_source_name(filename):
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

def ingest_csv_to_db(csv_dir, db_path, incremental=True, interactive=False):
    """
    Import CSV files into the database. 
    If incremental=True, only import transactions newer than the last import date.
    If interactive=True, prompt for custom source names.
    """
    conn = sqlite3.connect(db_path)
    
    # Ensure the import log table exists
    create_import_log_table(conn)

    # First, list all files
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

def rename_columns(df, source):
    """
    Rename columns using the mapping dictionaries for each bank.
    
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

#### switching from SQLITE3 to DUCKDB embedded. Launching into NEXT.JS

def consolidate_transactions(db_path):
    """
    Consolidate transactions from all sources into a single table
    with a unified schema for analysis.
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

def add_classification_columns(db_path):
    """Add columns for classification if they don't already exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # SQLite's ALTER TABLE doesn't support IF NOT EXISTS, so we use try/except.
    for col_def in [
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
    ]:
        col, col_type = col_def
        try:
            cursor.execute(f"ALTER TABLE consolidated_transactions ADD COLUMN {col} {col_type};")
            print(f"Added column {col} to consolidated_transactions")
        except sqlite3.OperationalError as e:
            print(f"Column probably already exists: {col}")
            # Likely the column already exists
            pass
    conn.commit()
    conn.close()


    ## Take a sample from the transactions to test 
def sample_transactions(db_path, fraction=0.10):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Count the total transactions in the consolidated table.
    cursor.execute("SELECT COUNT(*) FROM consolidated_transactions")
    total = cursor.fetchone()[0]
    
    # Calculate sample size (ensuring at least one row is returned).
    sample_size = max(1, int(total * fraction))
    print(f"Total transactions: {total}, sampling: {sample_size}")

    # Randomly select sample_size transactions.
    cursor.execute(
        "SELECT * FROM consolidated_transactions ORDER BY RANDOM() LIMIT ?",
        (sample_size,)
    )
    sample = cursor.fetchall()
    conn.close()
    return sample

def detect_recurring_transactions(db_path):
    """
    Detect recurring transactions by finding similar descriptions and amounts on a monthly basis.
    
    This function identifies transactions that appear monthly with similar descriptions and amounts,
    and marks them as recurring in the database.
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

def interactive_classification(db_path, sample_size=5, mode='all'):
    """
    Pull a sample of unlabeled transactions and let the user classify them.
    
    Args:
        db_path: Path to the database
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



def list_import_history(db_path):
    """List the import history from the import_log table"""
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
    
def get_classifier_dataset(db_path):
    """
    Extract dataset for training the rental expense classifier.
    
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

def train_rental_classifier(db_path, model_dir):
    """
    Train a machine learning model to classify transactions as rental-related.
    
    Args:
        db_path: Path to the database
        model_dir: Directory to save the trained model
    
    Returns:
        The trained model and accuracy metrics
    """
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

def get_latest_model(model_dir):
    """Get the most recently trained model"""
    latest_model_path = os.path.join(model_dir, "latest_rental_classifier.joblib")
    if os.path.exists(latest_model_path):
        return joblib.load(latest_model_path)
    return None

def batch_predict_rentals(db_path, model_dir, limit=100):
    """
    Use ML model to predict rental classification for unclassified transactions
    
    Args:
        db_path: Path to the database
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

def show_transaction_summary(db_path):
    """Show a summary of transactions in the database"""
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

if __name__ == "__main__":
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Budgeting App - Transaction Import Tool')
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
                        
    args = parser.parse_args()
    
    # Show import history if requested
    if args.history:
        list_import_history(db_path)
    
    # Show transaction summary if requested
    if args.summary:
        show_transaction_summary(db_path)
    
    # Run the import with incremental flag based on args
    if not (args.history or args.summary or args.train_model or args.predict or args.detect_recurring) or args.full or args.consolidate or args.classify:
        ingest_csv_to_db(csv_dir, db_path, 
                          incremental=not args.full,
                          interactive=args.interactive)
        
    # Consolidate if requested
    if args.consolidate:
        consolidate_transactions(db_path)
        add_classification_columns(db_path)
    
    # Auto-detect recurring transactions if requested
    if args.detect_recurring:
        detect_recurring_transactions(db_path)
    
    # Run classification if requested
    if args.classify:
        interactive_classification(db_path, sample_size=args.sample_size, mode=args.mode)
        
    # Train ML model if requested
    if args.train_model:
        train_rental_classifier(db_path, model_dir)
        
    # Use ML model to predict classifications
    if args.predict:
        batch_predict_rentals(db_path, model_dir, limit=args.predict_limit)




chase = {
    'posting_date':'date_posted',
    'type':'category',
    'amount':'amount',
    'description':'description',
    'details':'details',
    'balance':'balance',
    'check_or_slip':'check'
}

discover = {
    'post_date':'date_posted',
    'trans_date':'date_trans',
    'amount':'amount',
    'description':'description',
    'category':'category',
    'balance':'balance'
}

amex_plat = {}


"""
Table: Discover-2023-expenses 
Schema:
trans_date, Type: TEXT, NotNull: False, Default: None, Primary Key: False
post_date, Type: TEXT, NotNull: False, Default: None, Primary Key: False
description, Type: TEXT, NotNull: False, Default: None, Primary Key: False
amount, Type: REAL, NotNull: False, Default: None, Primary Key: False
category, Type: TEXT, NotNull: False, Default: None, Primary Key: False
"""


"""
('2023-AMEX-PLAT-TRANSACTIONS',)
Table: 2023-AMEX-PLAT-TRANSACTIONS

Schema: 
date, Type: TEXT, NotNull: False, Default: None, Primary Key: False
description, Type: TEXT, NotNull: False, Default: None, Primary Key: False
card_member, Type: TEXT, NotNull: False, Default: None, Primary Key: False
account_, Type: INTEGER, NotNull: False, Default: None, Primary Key: False
amount, Type: REAL, NotNull: False, Default: None, Primary Key: False
extended_details, Type: TEXT, NotNull: False, Default: None, Primary Key: False
appears_on_your_statement_as, Type: TEXT, NotNull: False, Default: None, Primary Key: False
address, Type: TEXT, NotNull: False, Default: None, Primary Key: False
city_state, Type: TEXT, NotNull: False, Default: None, Primary Key: False
zip_code, Type: TEXT, NotNull: False, Default: None, Primary Key: False
country, Type: TEXT, NotNull: False, Default: None, Primary Key: False
reference, Type: REAL, NotNull: False, Default: None, Primary Key: False
category, Type: TEXT, NotNull: False, Default: None, Primary Key: False
rego_rental, Type: TEXT, NotNull: False, Default: None, Primary Key: False
utilities, Type: TEXT, NotNull: False, Default: None, Primary Key: False
"""


"""
('2023-AMEX-ROSE-Transactions',)
Table: 2023-AMEX-ROSE-Transactions
Schema:
date, Type: TEXT, NotNull: False, Default: None, Primary Key: False
description, Type: TEXT, NotNull: False, Default: None, Primary Key: False
amount, Type: REAL, NotNull: False, Default: None, Primary Key: False
extended_details, Type: TEXT, NotNull: False, Default: None, Primary Key: False
appears_on_your_statement_as, Type: TEXT, NotNull: False, Default: None, Primary Key: False
address, Type: TEXT, NotNull: False, Default: None, Primary Key: False
city_state, Type: TEXT, NotNull: False, Default: None, Primary Key: False
zip_code, Type: TEXT, NotNull: False, Default: None, Primary Key: False
country, Type: TEXT, NotNull: False, Default: None, Primary Key: False
reference, Type: REAL, NotNull: False, Default: None, Primary Key: False
category, Type: TEXT, NotNull: False, Default: None, Primary Key: False
"""

""" Table: 2023-AMEX-ROSE-Transactions
Schema:
date, Type: TEXT, NotNull: False, Default: None, Primary Key: False
description, Type: TEXT, NotNull: False, Default: None, Primary Key: False
appears_on_your_statement_as, Type: TEXT, NotNull: False, Default: None, Primary Key: False
address, Type: TEXT, NotNull: False, Default: None, Primary Key: False
city_state, Type: TEXT, NotNull: False, Default: None, Primary Key: False
zip_code, Type: TEXT, NotNull: False, Default: None, Primary Key: False
country, Type: TEXT, NotNull: False, Default: None, Primary Key: False
reference, Type: REAL, NotNull: False, Default: None, Primary Key: False
category, Type: TEXT, NotNull: False, Default: None, Primary Key: False

"""

