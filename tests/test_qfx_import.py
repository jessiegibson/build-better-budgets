#!/usr/bin/env python3
"""
Test script for QFX file import
"""

import os
import sys
import pandas as pd
from datetime import datetime

# Add the parent directory to the path so we can import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ingestion.data_ingestion import (
    initialize_database, 
    import_qfx_files,
    get_transaction_summary
)

def test_qfx_import():
    """Test importing a QFX file"""
    # Initialize the database
    initialize_database()
    
    # Path to QFX directory
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    qfx_dir = os.path.join(current_dir, 'data', 'qfx')
    
    # Import QFX files
    results = import_qfx_files(qfx_dir, interactive=False, full_import=True)
    
    total_count = sum(results.values())
    print(f"Imported {total_count} records from QFX files:")
    for source, count in results.items():
        print(f"  - {source}: {count} records")
    
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
    
    return total_count > 0

if __name__ == "__main__":
    test_result = test_qfx_import()
    print(f"\nTest {'passed' if test_result else 'failed'}")
    sys.exit(0 if test_result else 1)