#!/usr/bin/env python3
"""
Test script for the ingestion module
"""

import os
import sys
import pandas as pd
from datetime import datetime

# Add the parent directory to the path so we can import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ingestion.data_ingestion import (
    initialize_database, 
    import_csv_file, 
    import_all_csv_files,
    get_transaction_summary
)

def test_csv_import():
    """Test importing a CSV file"""
    # Initialize the database
    initialize_database()
    
    # Path to test CSV
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_csv_path = os.path.join(current_dir, 'data', 'csv', 'chase_test.csv')
    
    # Import the CSV file
    source, count = import_csv_file(test_csv_path, interactive=False, full_import=True)
    
    print(f"Imported {count} records from {source}")
    
    # Get transaction summary
    summary = get_transaction_summary()
    print("\nTransaction Summary:")
    print(f"  - Total records: {summary['record_count']}")
    if summary['date_range']['first_date']:
        print(f"  - Date range: {summary['date_range']['first_date']} to {summary['date_range']['last_date']}")
    if 'amount_summary' in summary:
        print(f"  - Spending: ${abs(summary['amount_summary']['spending'] or 0):.2f}")
        print(f"  - Income: ${summary['amount_summary']['income'] or 0:.2f}")
        print(f"  - Net: ${summary['amount_summary']['net'] or 0:.2f}")
    
    return count > 0

if __name__ == "__main__":
    test_result = test_csv_import()
    print(f"\nTest {'passed' if test_result else 'failed'}")
    sys.exit(0 if test_result else 1)