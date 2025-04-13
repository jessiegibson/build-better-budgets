"""
Tax Management Module

Provides functionality for tracking tax-deductible expenses, depreciation,
and Section 179 deductions for business equipment and rental properties.
"""

import os
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Union

# Import local modules
from src.data_ingestion import get_db_connection

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TaxItem:
    """Class for managing tax-related items such as depreciable assets."""
    
    def __init__(self, item_id: Optional[int] = None):
        """
        Initialize a tax item, optionally loading an existing one.
        
        Args:
            item_id: ID of an existing tax item to load (optional)
        """
        self.id = item_id
        self.description = ""
        self.purchase_date = None
        self.amount = 0.0
        self.business_use_percentage = 100.0
        self.depreciation_years = 5
        self.use_section_179 = False
        self.transaction_id = None
        self.tax_year = datetime.now().year
        self.deduction_taken = 0.0
        self.notes = ""
        
        if item_id is not None:
            self.load_item(item_id)
    
    def load_item(self, item_id: int) -> bool:
        """
        Load an existing tax item from the database.
        
        Args:
            item_id: ID of the item to load
            
        Returns:
            True if the item was found and loaded, False otherwise
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Load item details
        cursor.execute("""
            SELECT 
                description, purchase_date, amount, business_use_percentage,
                depreciation_years, use_section_179, transaction_id,
                tax_year, deduction_taken, notes
            FROM tax_items
            WHERE id = ?
        """, (item_id,))
        
        item = cursor.fetchone()
        if not item:
            conn.close()
            return False
        
        self.id = item_id
        self.description = item['description']
        self.purchase_date = item['purchase_date']
        self.amount = item['amount']
        self.business_use_percentage = item['business_use_percentage']
        self.depreciation_years = item['depreciation_years']
        self.use_section_179 = bool(item['use_section_179'])
        self.transaction_id = item['transaction_id']
        self.tax_year = item['tax_year']
        self.deduction_taken = item['deduction_taken']
        self.notes = item['notes']
        
        conn.close()
        return True
    
    def save(self) -> int:
        """
        Save the tax item to the database.
        
        Returns:
            ID of the saved item
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if self.id is None:
            # Create new item
            cursor.execute("""
                INSERT INTO tax_items (
                    description, purchase_date, amount, business_use_percentage,
                    depreciation_years, use_section_179, transaction_id,
                    tax_year, deduction_taken, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.description,
                self.purchase_date,
                self.amount,
                self.business_use_percentage,
                self.depreciation_years,
                1 if self.use_section_179 else 0,
                self.transaction_id,
                self.tax_year,
                self.deduction_taken,
                self.notes
            ))
            
            self.id = cursor.lastrowid
        else:
            # Update existing item
            cursor.execute("""
                UPDATE tax_items
                SET description = ?, purchase_date = ?, amount = ?, business_use_percentage = ?,
                    depreciation_years = ?, use_section_179 = ?, transaction_id = ?,
                    tax_year = ?, deduction_taken = ?, notes = ?
                WHERE id = ?
            """, (
                self.description,
                self.purchase_date,
                self.amount,
                self.business_use_percentage,
                self.depreciation_years,
                1 if self.use_section_179 else 0,
                self.transaction_id,
                self.tax_year,
                self.deduction_taken,
                self.notes,
                self.id
            ))
        
        conn.commit()
        conn.close()
        
        return self.id
    
    def delete(self) -> bool:
        """
        Delete the tax item from the database.
        
        Returns:
            True if the item was deleted, False otherwise
        """
        if self.id is None:
            return False
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Delete depreciation history records
        cursor.execute("DELETE FROM tax_depreciation_history WHERE tax_item_id = ?", (self.id,))
        
        # Delete item
        cursor.execute("DELETE FROM tax_items WHERE id = ?", (self.id,))
        
        conn.commit()
        conn.close()
        
        self.id = None
        return True
    
    def calculate_depreciation(self, tax_year: int) -> Tuple[float, float]:
        """
        Calculate depreciation amount for a specific tax year.
        
        Args:
            tax_year: The tax year to calculate depreciation for
            
        Returns:
            Tuple of (regular_depreciation, section_179_deduction)
        """
        # Purchase year
        purchase_year = int(datetime.strptime(self.purchase_date, '%Y-%m-%d').year)
        
        # Calculate business use amount
        business_amount = self.amount * (self.business_use_percentage / 100.0)
        
        # Section 179 is only available in the purchase year
        section_179_amount = 0.0
        if self.use_section_179 and tax_year == purchase_year:
            section_179_amount = business_amount
            regular_depreciation = 0.0
            return regular_depreciation, section_179_amount
        
        # Regular depreciation (straight-line with half-year convention)
        if tax_year < purchase_year or tax_year > purchase_year + self.depreciation_years:
            # Outside of depreciation period
            regular_depreciation = 0.0
        elif tax_year == purchase_year:
            # First year (half-year convention)
            regular_depreciation = business_amount / self.depreciation_years / 2
        elif tax_year == purchase_year + self.depreciation_years:
            # Last year (half-year convention)
            regular_depreciation = business_amount / self.depreciation_years / 2
        else:
            # Full year
            regular_depreciation = business_amount / self.depreciation_years
        
        return regular_depreciation, section_179_amount
    
    def record_depreciation(self, tax_year: int) -> None:
        """
        Record depreciation for a specific tax year.
        
        Args:
            tax_year: The tax year to record depreciation for
        """
        if self.id is None:
            raise ValueError("Tax item must be saved before recording depreciation")
        
        # Calculate depreciation amounts
        regular_depreciation, section_179_amount = self.calculate_depreciation(tax_year)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if we already have a record for this tax year
        cursor.execute("""
            SELECT id FROM tax_depreciation_history
            WHERE tax_item_id = ? AND tax_year = ?
        """, (self.id, tax_year))
        
        record = cursor.fetchone()
        
        if record:
            # Update existing record
            cursor.execute("""
                UPDATE tax_depreciation_history
                SET depreciation_amount = ?, section_179_amount = ?
                WHERE id = ?
            """, (regular_depreciation, section_179_amount, record['id']))
        else:
            # Create new record
            cursor.execute("""
                INSERT INTO tax_depreciation_history
                (tax_item_id, tax_year, depreciation_amount, section_179_amount)
                VALUES (?, ?, ?, ?)
            """, (self.id, tax_year, regular_depreciation, section_179_amount))
        
        # Update total deduction taken
        deduction = regular_depreciation + section_179_amount
        
        cursor.execute("""
            UPDATE tax_items
            SET deduction_taken = deduction_taken + ?
            WHERE id = ?
        """, (deduction, self.id))
        
        self.deduction_taken += deduction
        
        conn.commit()
        conn.close()
    
    def get_depreciation_schedule(self) -> List[Dict[str, Any]]:
        """
        Get the full depreciation schedule for this item.
        
        Returns:
            List of year-by-year depreciation records
        """
        if not self.purchase_date:
            return []
        
        purchase_year = int(datetime.strptime(self.purchase_date, '%Y-%m-%d').year)
        
        # Create a schedule for each year in the depreciation period
        schedule = []
        
        for year in range(purchase_year, purchase_year + self.depreciation_years + 1):
            regular_depreciation, section_179_amount = self.calculate_depreciation(year)
            
            schedule.append({
                'year': year,
                'regular_depreciation': regular_depreciation,
                'section_179_amount': section_179_amount,
                'total_deduction': regular_depreciation + section_179_amount
            })
        
        return schedule


def get_all_tax_items() -> List[Dict[str, Any]]:
    """
    Get a list of all tax items.
    
    Returns:
        List of tax item dictionaries
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, description, purchase_date, amount, business_use_percentage,
               depreciation_years, use_section_179, tax_year, deduction_taken
        FROM tax_items
        ORDER BY purchase_date DESC
    """)
    
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return items


def get_section_179_limit(tax_year: int) -> float:
    """
    Get the Section 179 deduction limit for a specific tax year.
    
    Args:
        tax_year: The tax year
        
    Returns:
        Section 179 deduction limit for that year
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Look up the limit in tax_settings
    cursor.execute("""
        SELECT setting_value
        FROM tax_settings
        WHERE setting_name = ?
    """, (f"section_179_limit_{tax_year}",))
    
    result = cursor.fetchone()
    conn.close()
    
    if result and result['setting_value']:
        return float(result['setting_value'])
    
    # Default limits if not found in settings
    default_limits = {
        2023: 1160000,
        2024: 1220000,
        2025: 1250000,  # Projected
    }
    
    return default_limits.get(tax_year, 1000000)  # Default to $1M if year not listed


def calculate_tax_deductions(tax_year: int) -> float:
    """
    Calculate total tax deductions for a specific year.
    
    Args:
        tax_year: The tax year
        
    Returns:
        Total deduction amount
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get total deductions from tax_depreciation_history
    cursor.execute("""
        SELECT SUM(depreciation_amount + section_179_amount) as total
        FROM tax_depreciation_history
        WHERE tax_year = ?
    """, (tax_year,))
    
    result = cursor.fetchone()
    conn.close()
    
    return float(result['total']) if result and result['total'] else 0.0


def create_tax_depreciation_report(tax_year: int) -> Dict[str, Any]:
    """
    Generate a tax depreciation report for a specific year.
    
    Args:
        tax_year: The tax year to report on
        
    Returns:
        Dictionary with tax report data
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get total section 179 deductions
    cursor.execute("""
        SELECT SUM(section_179_amount) as total
        FROM tax_depreciation_history
        WHERE tax_year = ?
    """, (tax_year,))
    
    section_179_total = cursor.fetchone()['total'] or 0.0
    
    # Get total regular depreciation
    cursor.execute("""
        SELECT SUM(depreciation_amount) as total
        FROM tax_depreciation_history
        WHERE tax_year = ?
    """, (tax_year,))
    
    depreciation_total = cursor.fetchone()['total'] or 0.0
    
    # Get all items with deductions for this year
    cursor.execute("""
        SELECT 
            t.id, t.description, t.purchase_date, t.amount, 
            t.business_use_percentage, t.depreciation_years, t.use_section_179,
            h.depreciation_amount, h.section_179_amount
        FROM tax_items t
        JOIN tax_depreciation_history h ON t.id = h.tax_item_id
        WHERE h.tax_year = ?
        ORDER BY t.purchase_date
    """, (tax_year,))
    
    item_records = cursor.fetchall()
    conn.close()
    
    # Process items
    items = []
    for record in item_records:
        items.append({
            'id': record['id'],
            'description': record['description'],
            'purchase_date': record['purchase_date'],
            'amount': record['amount'],
            'business_use_percentage': record['business_use_percentage'],
            'depreciation_years': record['depreciation_years'],
            'use_section_179': bool(record['use_section_179']),
            'depreciation_amount': record['depreciation_amount'],
            'section_179_amount': record['section_179_amount'],
            'total_deduction': record['depreciation_amount'] + record['section_179_amount']
        })
    
    return {
        'tax_year': tax_year,
        'section_179_total': section_179_total,
        'depreciation_total': depreciation_total,
        'total_deductions': section_179_total + depreciation_total,
        'items': items,
        'section_179_limit': get_section_179_limit(tax_year)
    }


def convert_transaction_to_tax_item(transaction_id: int, 
                                   depreciation_years: int = 5,
                                   use_section_179: bool = False) -> int:
    """
    Convert a transaction to a tax item for depreciation tracking.
    
    Args:
        transaction_id: ID of the transaction to convert
        depreciation_years: Number of years to depreciate (default: 5)
        use_section_179: Whether to use Section 179 deduction (default: False)
        
    Returns:
        ID of the created tax item
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get transaction details
    cursor.execute("""
        SELECT date_posted, description, amount
        FROM consolidated_transactions
        WHERE id = ?
    """, (transaction_id,))
    
    transaction = cursor.fetchone()
    conn.close()
    
    if not transaction:
        raise ValueError(f"Transaction {transaction_id} not found")
    
    # Create tax item
    item = TaxItem()
    item.description = transaction['description']
    item.purchase_date = transaction['date_posted']
    item.amount = abs(transaction['amount'])  # Use absolute value
    item.depreciation_years = depreciation_years
    item.use_section_179 = use_section_179
    item.transaction_id = transaction_id
    item.tax_year = int(datetime.strptime(transaction['date_posted'], '%Y-%m-%d').year)
    
    # Save item
    item_id = item.save()
    
    # Record first year depreciation
    item.record_depreciation(item.tax_year)
    
    return item_id


if __name__ == "__main__":
    print("Tax Management Module")
    
    # Example usage
    tax_year = datetime.now().year
    
    # Get existing tax items
    items = get_all_tax_items()
    
    print(f"\nCurrent Tax Items: {len(items)}")
    for item in items:
        print(f"  {item['description']}: ${item['amount']:.2f}, "
              f"Deduction taken: ${item['deduction_taken']:.2f}")
    
    # Generate a tax report
    report = create_tax_depreciation_report(tax_year)
    
    print(f"\nTax Deductions for {tax_year}:")
    print(f"Section 179 deductions: ${report['section_179_total']:.2f}")
    print(f"Regular depreciation: ${report['depreciation_total']:.2f}")
    print(f"Total deductions: ${report['total_deductions']:.2f}")