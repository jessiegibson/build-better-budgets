#!/usr/bin/env python3
"""
Test script for QFX file parsing
"""

import os
import sys
import pandas as pd
from datetime import datetime

# Add the parent directory to the path so we can import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ingestion.qfx_importer import parse_qfx_file, qfx_to_csv

def test_qfx_parsing():
    """Test parsing a QFX file directly"""
    # Path to test QFX
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_qfx_path = os.path.join(current_dir, 'data', 'qfx', 'test.qfx')
    
    # Parse the QFX file
    transactions_df = parse_qfx_file(test_qfx_path)
    
    print(f"Parsed {len(transactions_df)} transactions from QFX file")
    if not transactions_df.empty:
        print("\nTransaction Data:")
        print(transactions_df)
    
    # Try converting to CSV
    csv_path = qfx_to_csv(test_qfx_path)
    print(f"\nConverted QFX to CSV: {csv_path}")
    
    return len(transactions_df) > 0

if __name__ == "__main__":
    test_result = test_qfx_parsing()
    print(f"\nTest {'passed' if test_result else 'failed'}")
    sys.exit(0 if test_result else 1)