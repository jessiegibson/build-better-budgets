"""
PDF Transaction Extractor

This module provides functions for extracting transaction data from various PDF formats.
It supports bank statements, credit card statements, and other financial documents.
"""

import os
import re
import pandas as pd
import pdfplumber
import tabula
import logging
from typing import List, Dict, Any, Optional, Tuple, Union

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# List of known PDF statement formats
PDF_FORMATS = {
    'chase': {
        'keywords': ['chase', 'jpmorgan'],
        'date_patterns': [r'\d{2}/\d{2}/\d{4}', r'\d{2}/\d{2}/\d{2}'],
        'amount_patterns': [r'\$[\d,]+\.\d{2}', r'-?\$[\d,]+\.\d{2}'],
        'table_areas': [(100, 200, 700, 500)]  # Example coordinates: [left, top, right, bottom]
    },
    'amex': {
        'keywords': ['american express', 'amex'],
        'date_patterns': [r'\d{2}/\d{2}/\d{2}', r'\d{2}/\d{2}/\d{4}'],
        'amount_patterns': [r'\$[\d,]+\.\d{2}', r'-?\$[\d,]+\.\d{2}'],
        'table_areas': None  # Detect automatically
    },
    'discover': {
        'keywords': ['discover', 'discover card'],
        'date_patterns': [r'\d{2}/\d{2}/\d{2}', r'\d{2}/\d{2}'],
        'amount_patterns': [r'\$[\d,]+\.\d{2}', r'-?\$[\d,]+\.\d{2}'],
        'table_areas': None  # Detect automatically
    },
    'home_depot': {
        'keywords': ['home depot', 'thd'],
        'date_patterns': [r'\d{2}/\d{2}/\d{4}', r'\d{2}/\d{2}/\d{2}'],
        'amount_patterns': [r'\$[\d,]+\.\d{2}', r'-?\$[\d,]+\.\d{2}'],
        'table_areas': None  # Detect automatically
    },
    'receipt': {
        'keywords': ['receipt', 'invoice', 'thank you for your purchase'],
        'date_patterns': [r'\d{2}/\d{2}/\d{4}', r'\d{2}/\d{2}/\d{2}', r'\d{2}-\d{2}-\d{4}'],
        'amount_patterns': [r'\$[\d,]+\.\d{2}', r'total:?\s*\$[\d,]+\.\d{2}', r'subtotal:?\s*\$[\d,]+\.\d{2}'],
        'table_areas': None  # Detect automatically
    }
}

def detect_pdf_format(pdf_path: str) -> Tuple[str, Dict[str, Any]]:
    """
    Detect the format of a PDF by analyzing its content.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Tuple of (format_name, format_config)
    """
    # Extract text from the first few pages
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        # Read up to 3 pages or all pages if fewer
        for i, page in enumerate(pdf.pages):
            if i >= 3:
                break
            text += page.extract_text().lower()
    
    # Check for keywords in the text
    for format_name, format_config in PDF_FORMATS.items():
        keywords = format_config['keywords']
        for keyword in keywords:
            if keyword.lower() in text:
                logger.info(f"Detected PDF format: {format_name}")
                return format_name, format_config
    
    # If no format detected, use generic approach
    logger.info("No specific format detected, using generic approach")
    return 'generic', {
        'keywords': [],
        'date_patterns': [r'\d{2}/\d{2}/\d{4}', r'\d{2}/\d{2}/\d{2}', r'\d{2}-\d{2}-\d{4}'],
        'amount_patterns': [r'\$[\d,]+\.\d{2}', r'-?\$[\d,]+\.\d{2}'],
        'table_areas': None
    }

def extract_tables_from_pdf(pdf_path: str, format_config: Dict[str, Any]) -> List[pd.DataFrame]:
    """
    Extract tables from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        format_config: Format configuration dictionary
        
    Returns:
        List of pandas DataFrames containing tables
    """
    tables = []
    
    # Try tabula-java first (handles structured tables better)
    try:
        if format_config['table_areas']:
            # Use specific table areas if provided
            tabs = tabula.read_pdf(
                pdf_path,
                pages='all',
                multiple_tables=True,
                area=format_config['table_areas'],
                lattice=True
            )
        else:
            # Auto-detect tables
            tabs = tabula.read_pdf(
                pdf_path,
                pages='all',
                multiple_tables=True,
                lattice=True
            )
        
        # Filter out empty tables
        for df in tabs:
            if not df.empty and df.shape[0] > 1 and df.shape[1] > 1:
                tables.append(df)
        
        if tables:
            logger.info(f"Extracted {len(tables)} tables using tabula")
            return tables
    except Exception as e:
        logger.warning(f"Tabula extraction failed: {e}")
    
    # Fall back to pdfplumber if tabula didn't work
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    if table and len(table) > 1 and len(table[0]) > 1:
                        # Convert to pandas DataFrame
                        df = pd.DataFrame(table[1:], columns=table[0])
                        tables.append(df)
        
        if tables:
            logger.info(f"Extracted {len(tables)} tables using pdfplumber")
            return tables
    except Exception as e:
        logger.warning(f"PDFPlumber extraction failed: {e}")
    
    # If no tables found, try to extract text and create a simple DataFrame
    if not tables:
        logger.info("No tables found, trying to extract text")
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text_data = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        lines = text.split('\n')
                        for line in lines:
                            # Try to identify transaction lines based on date patterns
                            for pattern in format_config['date_patterns']:
                                if re.search(pattern, line):
                                    text_data.append([line])
                                    break
                
                if text_data:
                    df = pd.DataFrame(text_data, columns=['raw_text'])
                    tables.append(df)
        except Exception as e:
            logger.warning(f"Text extraction failed: {e}")
    
    return tables

def process_tables(tables: List[pd.DataFrame], format_name: str, format_config: Dict[str, Any], pdf_path: str = None) -> pd.DataFrame:
    """
    Process extracted tables into a standardized format.
    
    Args:
        tables: List of pandas DataFrames containing raw table data
        format_name: Name of the detected format
        format_config: Format configuration dictionary
        pdf_path: Optional path to the PDF file (needed for some formats)
        
    Returns:
        DataFrame with standardized columns
    """
    if not tables:
        return pd.DataFrame()
    
    # Process based on format
    if format_name == 'chase':
        return process_chase_tables(tables)
    elif format_name == 'amex':
        return process_amex_tables(tables)
    elif format_name == 'discover':
        return process_discover_tables(tables)
    elif format_name == 'receipt':
        return process_receipt_tables(tables, format_config, pdf_path)
    else:
        # Generic processing
        return process_generic_tables(tables, format_config)

def process_chase_tables(tables: List[pd.DataFrame]) -> pd.DataFrame:
    """Process Chase bank statement tables."""
    # Start with an empty DataFrame with standard columns
    result = pd.DataFrame(columns=['date', 'description', 'amount'])
    
    for df in tables:
        # Check if this looks like a transaction table
        columns = df.columns.str.lower()
        
        # Check for common column patterns in Chase statements
        date_col = None
        desc_col = None
        amount_col = None
        
        for col in columns:
            if any(x in str(col).lower() for x in ['date', 'posted']):
                date_col = col
            elif any(x in str(col).lower() for x in ['description', 'details']):
                desc_col = col
            elif any(x in str(col).lower() for x in ['amount']):
                amount_col = col
        
        # If we found the key columns, process this table
        if date_col and desc_col and amount_col:
            # Extract and standardize columns
            temp_df = pd.DataFrame()
            temp_df['date'] = df[date_col]
            temp_df['description'] = df[desc_col]
            temp_df['amount'] = df[amount_col]
            
            # Clean up amount column
            temp_df['amount'] = temp_df['amount'].astype(str).str.replace('$', '').str.replace(',', '')
            temp_df['amount'] = pd.to_numeric(temp_df['amount'], errors='coerce')
            
            # Add to result
            result = pd.concat([result, temp_df], ignore_index=True)
    
    if not result.empty:
        # Add source column
        result['source'] = 'chase'
    
    return result

def process_amex_tables(tables: List[pd.DataFrame]) -> pd.DataFrame:
    """Process American Express statement tables."""
    # Start with an empty DataFrame with standard columns
    result = pd.DataFrame(columns=['date', 'description', 'amount'])
    
    for df in tables:
        # Check if this looks like a transaction table
        columns = df.columns.str.lower()
        
        # Check for common column patterns in Amex statements
        date_col = None
        desc_col = None
        amount_col = None
        
        for col in columns:
            if any(x in str(col).lower() for x in ['date']):
                date_col = col
            elif any(x in str(col).lower() for x in ['description']):
                desc_col = col
            elif any(x in str(col).lower() for x in ['amount']):
                amount_col = col
        
        # If we found the key columns, process this table
        if date_col and desc_col and amount_col:
            # Extract and standardize columns
            temp_df = pd.DataFrame()
            temp_df['date'] = df[date_col]
            temp_df['description'] = df[desc_col]
            temp_df['amount'] = df[amount_col]
            
            # Clean up amount column
            temp_df['amount'] = temp_df['amount'].astype(str).str.replace('$', '').str.replace(',', '')
            temp_df['amount'] = pd.to_numeric(temp_df['amount'], errors='coerce')
            
            # Add to result
            result = pd.concat([result, temp_df], ignore_index=True)
    
    if not result.empty:
        # Add source column
        result['source'] = 'amex'
    
    return result

def process_discover_tables(tables: List[pd.DataFrame]) -> pd.DataFrame:
    """Process Discover card statement tables."""
    # Start with an empty DataFrame with standard columns
    result = pd.DataFrame(columns=['date', 'description', 'amount'])
    
    for df in tables:
        # Check if this looks like a transaction table
        columns = df.columns.str.lower()
        
        # Check for common column patterns in Discover statements
        date_col = None
        desc_col = None
        amount_col = None
        
        for col in columns:
            if any(x in str(col).lower() for x in ['date', 'trans date']):
                date_col = col
            elif any(x in str(col).lower() for x in ['description', 'transaction']):
                desc_col = col
            elif any(x in str(col).lower() for x in ['amount']):
                amount_col = col
        
        # If we found the key columns, process this table
        if date_col and desc_col and amount_col:
            # Extract and standardize columns
            temp_df = pd.DataFrame()
            temp_df['date'] = df[date_col]
            temp_df['description'] = df[desc_col]
            temp_df['amount'] = df[amount_col]
            
            # Clean up amount column
            temp_df['amount'] = temp_df['amount'].astype(str).str.replace('$', '').str.replace(',', '')
            temp_df['amount'] = pd.to_numeric(temp_df['amount'], errors='coerce')
            
            # Add to result
            result = pd.concat([result, temp_df], ignore_index=True)
    
    if not result.empty:
        # Add source column
        result['source'] = 'discover'
    
    return result

def process_receipt_tables(tables: List[pd.DataFrame], format_config: Dict[str, Any], pdf_path: str = None) -> pd.DataFrame:
    """Process receipt tables with item details."""
    # Start with an empty DataFrame with standard columns
    result = pd.DataFrame(columns=['date', 'description', 'amount'])
    
    # For receipts, we need to extract:
    # 1. The receipt date
    # 2. The total amount
    # 3. Possibly line items
    
    receipt_date = None
    total_amount = None
    line_items = []
    
    # First try to extract receipt date and total amount from all text
    if pdf_path:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text()
            
            # Look for dates
            for pattern in format_config['date_patterns']:
                date_matches = re.findall(pattern, text)
                if date_matches:
                    receipt_date = date_matches[0]
                    break
            
            # Look for total amount
            for pattern in format_config['amount_patterns']:
                if 'total' in pattern:
                    # Prioritize patterns with 'total' in them
                    total_matches = re.findall(pattern, text, re.IGNORECASE)
                    if total_matches:
                        total_amount = total_matches[0]
                        break
            
            # If no total-specific pattern matched, try general amount patterns
            if not total_amount:
                for pattern in format_config['amount_patterns']:
                    amount_matches = re.findall(pattern, text)
                    if amount_matches:
                        # Take the last one, which is often the total
                        total_amount = amount_matches[-1]
                        break
    
    # Process tables for line items
    for df in tables:
        # Check if this looks like a line items table
        if df.shape[1] >= 2:  # At least 2 columns (description and amount)
            for idx, row in df.iterrows():
                # Try to identify item and price columns
                item_col = None
                price_col = None
                
                for col in df.columns:
                    if price_col is None:
                        # Check if column contains price-like values
                        col_vals = df[col].astype(str)
                        price_matches = col_vals.str.match(r'^\$?\d+\.\d{2}$').sum()
                        price_percent = price_matches / len(col_vals) if len(col_vals) > 0 else 0
                        if price_percent > 0.5:  # More than half are price-like
                            price_col = col
                
                # If we found a price column, the item description is likely in another column
                if price_col is not None:
                    for col in df.columns:
                        if col != price_col:
                            # Assume the longest text column is the description
                            if item_col is None or df[col].astype(str).str.len().mean() > df[item_col].astype(str).str.len().mean():
                                item_col = col
                
                if item_col is not None and price_col is not None:
                    # Extract items and prices
                    items = df[item_col].fillna('').astype(str)
                    prices = df[price_col].astype(str).str.replace('$', '').str.replace(',', '')
                    prices = pd.to_numeric(prices, errors='coerce')
                    
                    for i, (item, price) in enumerate(zip(items, prices)):
                        if pd.notnull(price) and price > 0 and item.strip():
                            line_items.append({
                                'date': receipt_date,
                                'description': item.strip(),
                                'amount': price
                            })
    
    # If we have line items, create a DataFrame
    if line_items:
        result = pd.DataFrame(line_items)
    else:
        # Just add the receipt total as a single transaction
        if receipt_date and total_amount:
            # Extract the numeric amount from the total
            amount_str = re.sub(r'[^\d.]', '', total_amount)
            try:
                amount = float(amount_str)
                result = pd.DataFrame([{
                    'date': receipt_date,
                    'description': f"Receipt {os.path.basename(pdf_path)}",
                    'amount': amount
                }])
            except ValueError:
                logger.warning(f"Could not parse total amount: {total_amount}")
    
    if not result.empty:
        # Add source column
        result['source'] = 'receipt'
    
    return result

def process_generic_tables(tables: List[pd.DataFrame], format_config: Dict[str, Any]) -> pd.DataFrame:
    """Process tables with unknown format."""
    # Start with an empty DataFrame with standard columns
    result = pd.DataFrame(columns=['date', 'description', 'amount'])
    
    # For each table, try to identify date, description, and amount columns
    for df in tables:
        if df.empty or df.shape[1] < 2:
            continue
        
        # First, check column names
        columns = [str(col).lower() for col in df.columns]
        
        date_col = None
        desc_col = None
        amount_col = None
        
        # Try to identify columns by name
        for i, col in enumerate(columns):
            if date_col is None and any(x in col for x in ['date', 'time', 'when']):
                date_col = df.columns[i]
            elif desc_col is None and any(x in col for x in ['desc', 'detail', 'transaction', 'particular']):
                desc_col = df.columns[i]
            elif amount_col is None and any(x in col for x in ['amount', 'sum', 'total', 'price', 'cost']):
                amount_col = df.columns[i]
        
        # If we couldn't identify columns by name, try by content
        if date_col is None or desc_col is None or amount_col is None:
            # For each column, check content patterns
            for i, col in enumerate(df.columns):
                col_values = df[col].astype(str)
                
                # Check for date patterns
                if date_col is None:
                    date_matches = sum(col_values.str.match(pat).sum() for pat in format_config['date_patterns'])
                    if date_matches > len(df) * 0.5:  # More than half match date patterns
                        date_col = col
                
                # Check for amount patterns
                if amount_col is None:
                    amount_matches = sum(col_values.str.match(pat).sum() for pat in format_config['amount_patterns'])
                    if amount_matches > len(df) * 0.3:  # At least 30% match amount patterns
                        amount_col = col
            
            # For description, use the column with longest average text that is not date or amount
            if desc_col is None:
                max_len = 0
                for i, col in enumerate(df.columns):
                    if col != date_col and col != amount_col:
                        avg_len = df[col].astype(str).str.len().mean()
                        if avg_len > max_len:
                            max_len = avg_len
                            desc_col = col
        
        # If we identified all necessary columns, extract the data
        if date_col is not None and desc_col is not None and amount_col is not None:
            temp_df = pd.DataFrame()
            temp_df['date'] = df[date_col]
            temp_df['description'] = df[desc_col]
            temp_df['amount'] = df[amount_col]
            
            # Clean up amount column
            temp_df['amount'] = temp_df['amount'].astype(str).str.replace('$', '').str.replace(',', '')
            temp_df['amount'] = pd.to_numeric(temp_df['amount'], errors='coerce')
            
            # Add to result
            result = pd.concat([result, temp_df], ignore_index=True)
    
    return result

def extract_transactions_from_pdf(pdf_path: str) -> Tuple[pd.DataFrame, str]:
    """
    Extract transaction data from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Tuple of (DataFrame with transactions, detected source name)
    """
    logger.info(f"Processing PDF: {pdf_path}")
    
    # Detect PDF format
    format_name, format_config = detect_pdf_format(pdf_path)
    
    # Extract tables
    tables = extract_tables_from_pdf(pdf_path, format_config)
    
    # Process tables into standardized format
    if format_name == 'receipt':
        transactions_df = process_tables(tables, format_name, format_config, pdf_path)
    else:
        transactions_df = process_tables(tables, format_name, format_config)
    
    # Additional processing for specific source
    if format_name == 'receipt':
        # For receipts, set the filename as the source
        source = os.path.splitext(os.path.basename(pdf_path))[0]
    else:
        source = format_name
    
    if not transactions_df.empty:
        # Add source column if not present
        if 'source' not in transactions_df.columns:
            transactions_df['source'] = source
            
        logger.info(f"Extracted {len(transactions_df)} transactions from {pdf_path}")
    else:
        logger.warning(f"No transactions extracted from {pdf_path}")
    
    return transactions_df, source

def detect_date_format(date_str: str) -> Optional[str]:
    """
    Detect the format of a date string.
    
    Args:
        date_str: Date string to analyze
        
    Returns:
        String format for strptime, or None if format not detected
    """
    # Common date formats
    formats = [
        ('%m/%d/%Y', r'\d{1,2}/\d{1,2}/\d{4}'),
        ('%m/%d/%y', r'\d{1,2}/\d{1,2}/\d{2}'),
        ('%Y-%m-%d', r'\d{4}-\d{1,2}-\d{1,2}'),
        ('%m-%d-%Y', r'\d{1,2}-\d{1,2}-\d{4}'),
        ('%b %d, %Y', r'[A-Za-z]{3} \d{1,2}, \d{4}'),
        ('%B %d, %Y', r'[A-Za-z]+ \d{1,2}, \d{4}')
    ]
    
    for fmt, pattern in formats:
        if re.match(pattern, date_str):
            return fmt
    
    return None

def standardize_date(date_str: str) -> Optional[str]:
    """
    Convert various date formats to standard YYYY-MM-DD format.
    
    Args:
        date_str: Date string to standardize
        
    Returns:
        Standardized date string or None if conversion fails
    """
    from datetime import datetime
    
    if pd.isna(date_str) or not date_str:
        return None
    
    # Try to detect format
    fmt = detect_date_format(date_str)
    if fmt:
        try:
            # Convert to standard format
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            pass
    
    # Try pandas to_datetime as fallback
    try:
        dt = pd.to_datetime(date_str)
        return dt.strftime('%Y-%m-%d')
    except:
        return None

def pdf_to_csv(pdf_path: str, output_dir: str = None) -> str:
    """
    Convert a PDF file to CSV with standardized transaction format.
    
    Args:
        pdf_path: Path to the PDF file
        output_dir: Directory to save the CSV file (defaults to same directory as PDF)
        
    Returns:
        Path to the generated CSV file
    """
    # Extract transactions
    transactions_df, source = extract_transactions_from_pdf(pdf_path)
    
    if transactions_df.empty:
        logger.error(f"Failed to extract transactions from {pdf_path}")
        return None
    
    # Standardize dates
    if 'date' in transactions_df.columns:
        transactions_df['date'] = transactions_df['date'].apply(standardize_date)
        
    # Clean amounts
    if 'amount' in transactions_df.columns:
        # Make sure amounts are numeric
        transactions_df['amount'] = pd.to_numeric(transactions_df['amount'], errors='coerce')
    
    # Set output path
    if output_dir is None:
        output_dir = os.path.dirname(pdf_path)
    
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_path = os.path.join(output_dir, f"{base_name}_extracted.csv")
    
    # Save to CSV
    transactions_df.to_csv(output_path, index=False)
    logger.info(f"Saved extracted transactions to {output_path}")
    
    return output_path

def process_pdf_directory(pdf_dir: str, output_dir: str = None) -> List[str]:
    """
    Process all PDF files in a directory, extracting transactions to CSV.
    
    Args:
        pdf_dir: Directory containing PDF files
        output_dir: Directory to save CSV files (defaults to pdf_dir)
        
    Returns:
        List of generated CSV file paths
    """
    if output_dir is None:
        output_dir = pdf_dir
    
    os.makedirs(output_dir, exist_ok=True)
    
    csv_files = []
    
    # Find all PDF files
    for filename in os.listdir(pdf_dir):
        if filename.lower().endswith('.pdf'):
            pdf_path = os.path.join(pdf_dir, filename)
            try:
                csv_path = pdf_to_csv(pdf_path, output_dir)
                if csv_path:
                    csv_files.append(csv_path)
            except Exception as e:
                logger.error(f"Error processing {pdf_path}: {e}")
    
    return csv_files

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python pdf_extractor.py <pdf_file_or_directory>")
        sys.exit(1)
    
    path = sys.argv[1]
    
    if os.path.isdir(path):
        # Process directory
        csv_files = process_pdf_directory(path)
        print(f"Processed {len(csv_files)} PDF files:")
        for csv_file in csv_files:
            print(f"  - {csv_file}")
    elif os.path.isfile(path) and path.lower().endswith('.pdf'):
        # Process single file
        csv_path = pdf_to_csv(path)
        if csv_path:
            print(f"Extracted transactions saved to {csv_path}")
        else:
            print(f"Failed to extract transactions from {path}")
    else:
        print("Invalid path or not a PDF file.")
        sys.exit(1)