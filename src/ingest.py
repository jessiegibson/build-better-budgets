#!/usr/bin/env python3
"""
Main script for data ingestion.

This script provides a command-line interface for importing transaction data
from various sources (CSV, PDF, QFX) into the transaction database.
"""

import os
import sys
import argparse
import logging
from typing import Dict, Any, List

from ingestion.data_ingestion import (
    initialize_database,
    import_all_csv_files,
    import_pdf_files,
    import_qfx_files,
    get_transaction_summary,
    show_import_history
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_argparser() -> argparse.ArgumentParser:
    """Set up the argument parser for CLI arguments."""
    parser = argparse.ArgumentParser(description='Financial Data Importer')
    
    # Import options
    parser.add_argument('--csv-dir', type=str, help='Directory containing CSV files to import')
    parser.add_argument('--pdf-dir', type=str, help='Directory containing PDF files to import')
    parser.add_argument('--qfx-dir', type=str, help='Directory containing QFX files to import')
    
    # Import modes
    parser.add_argument('--full', action='store_true', help='Full import (ignores incremental checks)')
    parser.add_argument('--interactive', action='store_true', help='Interactive mode for source detection')
    
    # Summary and history
    parser.add_argument('--summary', action='store_true', help='Show transaction summary')
    parser.add_argument('--history', action='store_true', help='Show import history')
    
    return parser

def display_summary(summary: Dict[str, Any]) -> None:
    """Display a summary of the transaction database."""
    print("Transaction Summary:")
    print(f"  - Total records: {summary['record_count']}")
    
    if summary['date_range']['first_date']:
        print(f"  - Date range: {summary['date_range']['first_date']} to {summary['date_range']['last_date']}")
    
    if 'amount_summary' in summary:
        print(f"  - Spending: ${abs(summary['amount_summary']['spending']):.2f}")
        print(f"  - Income: ${summary['amount_summary']['income']:.2f}")
        print(f"  - Net: ${summary['amount_summary']['net']:.2f}")
    
    if 'classification' in summary:
        print("  - Classifications:")
        for key, value in summary['classification'].items():
            print(f"    - {key.replace('_count', '')}: {value}")
    
    if 'sources' in summary and summary['sources']:
        print("  - Sources:")
        for source in summary['sources']:
            print(f"    - {source['source']}: {source['count']} records")
    
    if 'top_categories' in summary and summary['top_categories']:
        print("  - Top categories:")
        for cat in summary['top_categories']:
            print(f"    - {cat['expense_category'] or 'Uncategorized'}: ${abs(cat['total']):.2f} ({cat['count']} transactions)")

def display_import_history(history: List[Dict[str, Any]]) -> None:
    """Display the import history."""
    print("Import History:")
    for record in history:
        print(f"  - {record['source']}: {record['filename']} ({record['record_count']} records on {record['import_date']})")

def main() -> int:
    """Main function for the import script."""
    parser = setup_argparser()
    args = parser.parse_args()
    
    # Initialize the database
    initialize_database()
    
    # Import data based on arguments
    import_count = 0
    
    if args.csv_dir:
        csv_results = import_all_csv_files(args.csv_dir, args.interactive, args.full)
        csv_count = sum(csv_results.values())
        import_count += csv_count
        print(f"Imported {csv_count} records from CSV files:")
        for source, count in csv_results.items():
            print(f"  - {source}: {count} records")
        print()
    
    if args.pdf_dir:
        pdf_results = import_pdf_files(args.pdf_dir, args.interactive, args.full)
        pdf_count = sum(pdf_results.values())
        import_count += pdf_count
        print(f"Imported {pdf_count} records from PDF files:")
        for source, count in pdf_results.items():
            print(f"  - {source}: {count} records")
        print()
    
    if args.qfx_dir:
        qfx_results = import_qfx_files(args.qfx_dir, args.interactive, args.full)
        qfx_count = sum(qfx_results.values())
        import_count += qfx_count
        print(f"Imported {qfx_count} records from QFX files:")
        for source, count in qfx_results.items():
            print(f"  - {source}: {count} records")
        print()
    
    # Show summary if requested
    if args.summary or import_count > 0:
        summary = get_transaction_summary()
        print()
        display_summary(summary)
    
    # Show import history if requested
    if args.history:
        history = show_import_history()
        print()
        display_import_history(history)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())