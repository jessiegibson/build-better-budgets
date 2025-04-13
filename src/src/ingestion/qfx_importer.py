"""
QFX File Importer

This module provides functions for extracting transaction data from QFX (Quicken) files.
It supports most financial institutions that provide QFX download format.
"""

import os
import re
import csv
import pandas as pd
import xml.etree.ElementTree as ET
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_qfx_file(qfx_path: str) -> pd.DataFrame:
    """
    Parse a QFX file and extract transaction data.
    
    Args:
        qfx_path: Path to the QFX file
        
    Returns:
        DataFrame with standardized transaction data
    """
    logger.info(f"Parsing QFX file: {qfx_path}")
    
    # Read the QFX file content
    with open(qfx_path, 'r', encoding='utf-8', errors='ignore') as file:
        content = file.read()
    
    # QFX files have a header section and an SGML/XML section
    # Find where the XML section starts
    ofx_start = content.find('<OFX>')
    if ofx_start == -1:
        logger.error(f"No OFX data found in {qfx_path}")
        return pd.DataFrame()
    
    # Extract the SGML/XML part
    ofx_content = content[ofx_start:]
    
    # QFX files are SGML, not strictly XML, so we need to clean it up
    # Replace SGML closing tags with proper XML closing tags
    ofx_content = re.sub(r'<([A-Z0-9_]+)>', r'<\1>', ofx_content)
    ofx_content = re.sub(r'</([A-Z0-9_]+)>', r'</\1>', ofx_content)
    
    # In some QFX files, tags may not be properly closed
    # This is a simplistic approach; more advanced SGML parsing might be needed
    try:
        # Try to parse as XML
        root = ET.fromstring(ofx_content)
    except ET.ParseError as e:
        logger.error(f"Failed to parse QFX content as XML: {e}")
        
        # Fall back to regex-based extraction
        return parse_qfx_with_regex(ofx_content)
    
    # Extract transactions from XML
    return extract_transactions_from_xml(root, os.path.basename(qfx_path))

def parse_qfx_with_regex(ofx_content: str) -> pd.DataFrame:
    """
    Parse QFX content using regex when XML parsing fails.
    
    Args:
        ofx_content: QFX content as string
        
    Returns:
        DataFrame with transactions
    """
    transactions = []
    
    # Find all transaction sections
    transaction_sections = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', ofx_content, re.DOTALL)
    
    for section in transaction_sections:
        transaction = {}
        
        # Extract date (posted date)
        date_match = re.search(r'<DTPOSTED>(.*?)</DTPOSTED>', section)
        if date_match:
            date_str = date_match.group(1)
            # Format: YYYYMMDD or YYYYMMDDHHMMSS
            try:
                if len(date_str) == 8:
                    dt = datetime.strptime(date_str, '%Y%m%d')
                elif len(date_str) == 14:
                    dt = datetime.strptime(date_str, '%Y%m%d%H%M%S')
                else:
                    # Try to handle other formats
                    dt = pd.to_datetime(date_str)
                
                transaction['date'] = dt.strftime('%Y-%m-%d')
            except:
                transaction['date'] = None
        
        # Extract amount
        amount_match = re.search(r'<TRNAMT>(.*?)</TRNAMT>', section)
        if amount_match:
            try:
                transaction['amount'] = float(amount_match.group(1))
            except:
                transaction['amount'] = None
        
        # Extract description/memo
        memo_match = re.search(r'<MEMO>(.*?)</MEMO>', section)
        name_match = re.search(r'<NAME>(.*?)</NAME>', section)
        
        if memo_match:
            transaction['description'] = memo_match.group(1)
        elif name_match:
            transaction['description'] = name_match.group(1)
        else:
            transaction['description'] = 'Unknown'
        
        # Extract check number if available
        check_match = re.search(r'<CHECKNUM>(.*?)</CHECKNUM>', section)
        if check_match:
            transaction['details'] = f"Check #{check_match.group(1)}"
        else:
            transaction['details'] = ""
        
        transactions.append(transaction)
    
    # Create DataFrame
    if transactions:
        df = pd.DataFrame(transactions)
        return df
    else:
        return pd.DataFrame()

def extract_transactions_from_xml(root: ET.Element, source_name: str) -> pd.DataFrame:
    """
    Extract transaction data from OFX/QFX XML structure.
    
    Args:
        root: XML root element
        source_name: Name of the source (e.g., filename)
        
    Returns:
        DataFrame with standardized transaction data
    """
    transactions = []
    
    # Find all transaction elements (could be in different places depending on QFX structure)
    for stmt_path in ['.//STMTTRN', './/CCSTMTTRN', './/INVSTMTTRN']:
        for trans_elem in root.findall(stmt_path):
            transaction = {}
            
            # Date (posted date)
            date_elem = trans_elem.find('DTPOSTED')
            if date_elem is not None and date_elem.text:
                date_str = date_elem.text
                # QFX dates are typically in format YYYYMMDD or YYYYMMDDHHMMSS
                try:
                    if len(date_str) == 8:
                        dt = datetime.strptime(date_str, '%Y%m%d')
                    elif len(date_str) == 14:
                        dt = datetime.strptime(date_str, '%Y%m%d%H%M%S')
                    else:
                        # Try to handle other formats
                        dt = pd.to_datetime(date_str)
                    
                    transaction['date'] = dt.strftime('%Y-%m-%d')
                except:
                    logger.warning(f"Could not parse date: {date_str}")
                    transaction['date'] = None
            
            # Amount
            amount_elem = trans_elem.find('TRNAMT')
            if amount_elem is not None and amount_elem.text:
                try:
                    transaction['amount'] = float(amount_elem.text)
                except:
                    logger.warning(f"Could not parse amount: {amount_elem.text}")
                    transaction['amount'] = None
            
            # Description - prefer MEMO, fallback to NAME
            memo_elem = trans_elem.find('MEMO')
            name_elem = trans_elem.find('NAME')
            
            if memo_elem is not None and memo_elem.text:
                transaction['description'] = memo_elem.text
            elif name_elem is not None and name_elem.text:
                transaction['description'] = name_elem.text
            else:
                transaction['description'] = 'Unknown'
            
            # Additional details - check number if available
            check_elem = trans_elem.find('CHECKNUM')
            if check_elem is not None and check_elem.text:
                transaction['details'] = f"Check #{check_elem.text}"
            else:
                transaction['details'] = ""
            
            transactions.append(transaction)
    
    # Create DataFrame
    if transactions:
        df = pd.DataFrame(transactions)
        
        # Add source column
        df['source'] = source_name
        
        logger.info(f"Extracted {len(df)} transactions from QFX")
        return df
    else:
        logger.warning("No transactions found in QFX file")
        return pd.DataFrame()

def qfx_to_csv(qfx_path: str, output_dir: str = None) -> str:
    """
    Convert a QFX file to CSV with standardized transaction format.
    
    Args:
        qfx_path: Path to the QFX file
        output_dir: Directory to save the CSV file (defaults to same directory as QFX)
        
    Returns:
        Path to the generated CSV file
    """
    # Extract transactions
    transactions_df = parse_qfx_file(qfx_path)
    
    if transactions_df.empty:
        logger.error(f"Failed to extract transactions from {qfx_path}")
        return None
    
    # Set output path
    if output_dir is None:
        output_dir = os.path.dirname(qfx_path)
    
    base_name = os.path.splitext(os.path.basename(qfx_path))[0]
    output_path = os.path.join(output_dir, f"{base_name}_extracted.csv")
    
    # Save to CSV
    transactions_df.to_csv(output_path, index=False)
    logger.info(f"Saved extracted transactions to {output_path}")
    
    return output_path

def process_qfx_directory(qfx_dir: str, output_dir: str = None) -> List[str]:
    """
    Process all QFX files in a directory, extracting transactions to CSV.
    
    Args:
        qfx_dir: Directory containing QFX files
        output_dir: Directory to save CSV files (defaults to qfx_dir)
        
    Returns:
        List of generated CSV file paths
    """
    if output_dir is None:
        output_dir = qfx_dir
    
    os.makedirs(output_dir, exist_ok=True)
    
    csv_files = []
    
    # Find all QFX files
    for filename in os.listdir(qfx_dir):
        if filename.lower().endswith('.qfx'):
            qfx_path = os.path.join(qfx_dir, filename)
            try:
                csv_path = qfx_to_csv(qfx_path, output_dir)
                if csv_path:
                    csv_files.append(csv_path)
            except Exception as e:
                logger.error(f"Error processing {qfx_path}: {e}")
    
    return csv_files

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python qfx_importer.py <qfx_file_or_directory>")
        sys.exit(1)
    
    path = sys.argv[1]
    
    if os.path.isdir(path):
        # Process directory
        csv_files = process_qfx_directory(path)
        print(f"Processed {len(csv_files)} QFX files:")
        for csv_file in csv_files:
            print(f"  - {csv_file}")
    elif os.path.isfile(path) and path.lower().endswith('.qfx'):
        # Process single file
        csv_path = qfx_to_csv(path)
        if csv_path:
            print(f"Extracted transactions saved to {csv_path}")
        else:
            print(f"Failed to extract transactions from {path}")
    else:
        print("Invalid path or not a QFX file.")
        sys.exit(1)