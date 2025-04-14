import os
import sys
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any, Union

# ---------------------------
# Tax Depreciation and Section 179
# ---------------------------

def get_section_179_limit(year: int) -> float:
    """
    Get the Section 179 deduction limit for a specific tax year.

    Args:
        year: Tax year

    Returns:
        Section 179 deduction limit
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    setting_name = f"section_179_limit_{year}"
    cursor.execute("SELECT setting_value FROM tax_settings WHERE setting_name = ?", (setting_name,))
    result = cursor.fetchone()

    if result:
        limit = float(result[0])
    else:
        # Default limit if not found
        limit = 1250000.0

    conn.close()
    return limit

def add_tax_item(description: str, purchase_date: str, amount: float,
                 business_use_percentage: int = 100, depreciation_years: int = 5,
                 use_section_179: bool = True, transaction_id: Optional[int] = None,
                 notes: Optional[str] = None) -> int:
    """
    Add a new tax item for Section 179 deduction or depreciation.

    Args:
        description: Item description
        purchase_date: Date of purchase in YYYY-MM-DD format
        amount: Purchase amount
        business_use_percentage: Percentage used for business (1-100)
        depreciation_years: Number of years for depreciation
        use_section_179: Whether to use Section 179 deduction
        transaction_id: Related transaction ID (optional)
        notes: Additional notes

    Returns:
        ID of the new tax item
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    current_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Extract tax year from purchase date
    tax_year = int(purchase_date.split('-')[0])

    cursor.execute("""
    INSERT INTO tax_items
    (description, purchase_date, amount, business_use_percentage,
     depreciation_years, use_section_179, transaction_id, notes,
     tax_year, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        description, purchase_date, amount, business_use_percentage,
        depreciation_years, 1 if use_section_179 else 0, transaction_id, notes,
        tax_year, current_timestamp, current_timestamp
    ))

    tax_item_id = cursor.lastrowid

    # If using Section 179, add to the depreciation history for the purchase year
    if use_section_179:
        # Calculate the Section 179 deduction amount (business portion of the cost)
        section_179_amount = amount * (business_use_percentage / 100)

        cursor.execute("""
        INSERT INTO tax_depreciation_history
        (tax_item_id, tax_year, depreciation_amount, section_179_amount, created_at)
        VALUES (?, ?, ?, ?, ?)
        """, (tax_item_id, tax_year, 0, section_179_amount, current_timestamp))

    conn.commit()
    conn.close()

    return tax_item_id

def update_tax_item(item_id: int, description: str, purchase_date: str, amount: float,
                   business_use_percentage: int = 100, depreciation_years: int = 5,
                   use_section_179: bool = True, notes: Optional[str] = None) -> bool:
    """
    Update an existing tax item.

    Args:
        item_id: ID of the tax item to update
        description: Item description
        purchase_date: Date of purchase in YYYY-MM-DD format
        amount: Purchase amount
        business_use_percentage: Percentage used for business (1-100)
        depreciation_years: Number of years for depreciation
        use_section_179: Whether to use Section 179 deduction
        notes: Additional notes

    Returns:
        True if successful, False otherwise
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    current_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Extract tax year from purchase date
    tax_year = int(purchase_date.split('-')[0])

    # Check if this item already has depreciation history
    cursor.execute("SELECT COUNT(*) FROM tax_depreciation_history WHERE tax_item_id = ?", (item_id,))
    has_history = cursor.fetchone()[0] > 0

    try:
        # Update the tax item
        cursor.execute("""
        UPDATE tax_items
        SET description = ?, purchase_date = ?, amount = ?,
            business_use_percentage = ?, depreciation_years = ?,
            use_section_179 = ?, notes = ?, tax_year = ?, updated_at = ?
        WHERE id = ?
        """, (
            description, purchase_date, amount, business_use_percentage,
            depreciation_years, 1 if use_section_179 else 0, notes,
            tax_year, current_timestamp, item_id
        ))

        # If it has no history yet, create initial entry
        if not has_history and use_section_179:
            # Calculate the Section 179 deduction amount
            section_179_amount = amount * (business_use_percentage / 100)

            cursor.execute("""
            INSERT INTO tax_depreciation_history
            (tax_item_id, tax_year, depreciation_amount, section_179_amount, created_at)
            VALUES (?, ?, ?, ?, ?)
            """, (item_id, tax_year, 0, section_179_amount, current_timestamp))

        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Error updating tax item: {e}")
        conn.rollback()
        conn.close()
        return False

def delete_tax_item(item_id: int) -> bool:
    """
    Delete a tax item and its depreciation history.

    Args:
        item_id: ID of the tax item to delete

    Returns:
        True if successful, False otherwise
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # The foreign key constraint should automatically delete related history
        cursor.execute("DELETE FROM tax_items WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Error deleting tax item: {e}")
        conn.rollback()
        conn.close()
        return False

def get_tax_items(tax_year: Optional[int] = None) -> List[Dict]:
    """
    Get all tax items, optionally filtered by tax year.

    Args:
        tax_year: Optional tax year to filter items

    Returns:
        List of tax item dictionaries
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if tax_year:
        cursor.execute("""
        SELECT * FROM tax_items
        WHERE tax_year = ?
        ORDER BY purchase_date DESC
        """, (tax_year,))
    else:
        cursor.execute("""
        SELECT * FROM tax_items
        ORDER BY purchase_date DESC
        """)

    items = [dict(row) for row in cursor.fetchall()]

    # Calculate business amount for each item
    for item in items:
        item['business_amount'] = item['amount'] * (item['business_use_percentage'] / 100)

        # Get depreciation history for this item
        cursor.execute("""
        SELECT * FROM tax_depreciation_history
        WHERE tax_item_id = ?
        ORDER BY tax_year ASC
        """, (item['id'],))

        item['depreciation_history'] = [dict(row) for row in cursor.fetchall()]

        # Calculate section 179 amount if applicable
        if item['use_section_179'] and item['depreciation_history']:
            item['section_179_amount'] = sum(hist['section_179_amount'] for hist in item['depreciation_history'])
        else:
            item['section_179_amount'] = 0

    conn.close()
    return items

def get_equipment_transactions() -> List[Dict]:
    """
    Get transactions that might be eligible for Section 179 or depreciation.

    Returns:
        List of transaction dictionaries
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get transactions marked as equipment_tools or with likely equipment categories
    cursor.execute("""
    SELECT id, date_posted, description, amount, category
    FROM consolidated_transactions
    WHERE (equipment_tools = 1 OR category IN ('Equipment', 'Office Equipment', 'Tools', 'Furniture', 'Computer'))
    AND amount < 0  -- Only expenses
    ORDER BY date_posted DESC
    LIMIT 100
    """)

    transactions = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return transactions

def calculate_depreciation(cost: float, years: int, year_purchased: int, current_year: int) -> float:
    """
    Calculate straight-line depreciation amount for the current year.

    Args:
        cost: Asset cost
        years: Depreciation period in years
        year_purchased: Year the asset was purchased
        current_year: Current tax year

    Returns:
        Depreciation amount for the current year
    """
    # Simple straight-line depreciation
    annual_depreciation = cost / years

    # Check if we're still within the depreciation period
    if current_year < year_purchased or current_year >= year_purchased + years:
        return 0

    # For first year, prorate based on purchase month
    if current_year == year_purchased:
        # Assume half-year convention for simplicity
        return annual_depreciation / 2

    # For last year, use the remaining amount
    if current_year == year_purchased + years - 1:
        # Also assume half-year convention for last year
        return annual_depreciation / 2

    # For all other years, use full annual depreciation
    return annual_depreciation

def generate_tax_report(tax_year: int) -> Dict:
    """
    Generate a comprehensive tax deduction report for a specific year.

    Args:
        tax_year: Tax year for the report

    Returns:
        Dictionary with report data
    """
    # Get section 179 limit for the year
    section_179_limit = get_section_179_limit(tax_year)

    # Get all tax items
    items = get_tax_items(tax_year)

    # Split into section 179 and regular depreciation items
    section_179_items = []
    depreciation_items = []

    section_179_total = 0
    depreciation_total = 0
    section_179_deduction = 0

    for item in items:
        purchase_year = int(item['purchase_date'].split('-')[0])

        # Calculate eligible amount (business percentage of cost)
        business_amount = item['amount'] * (item['business_use_percentage'] / 100)

        if item['use_section_179'] and purchase_year == tax_year:
            # Add to section 179 items if purchased in current tax year
            item['section_179_amount'] = business_amount
            section_179_total += business_amount
            section_179_items.append(item)
        else:
            # Calculate regular depreciation
            current_year_depreciation = calculate_depreciation(
                business_amount,
                item['depreciation_years'],
                purchase_year,
                tax_year
            )

            # Calculate prior depreciation
            prior_years = list(range(purchase_year, tax_year))
            prior_depreciation = sum(
                calculate_depreciation(business_amount, item['depreciation_years'], purchase_year, year)
                for year in prior_years
            )

            # Calculate remaining value
            total_depreciation = prior_depreciation + current_year_depreciation
            remaining_value = business_amount - total_depreciation

            # Add to depreciation items
            if current_year_depreciation > 0:
                item['current_year_depreciation'] = current_year_depreciation
                item['prior_depreciation'] = prior_depreciation
                item['remaining_value'] = max(0, remaining_value)
                depreciation_total += current_year_depreciation
                depreciation_items.append(item)

    # Apply section 179 limit
    if section_179_total > section_179_limit:
        # If over limit, calculate carryover
        section_179_deduction = section_179_limit
        section_179_carryover = section_179_total - section_179_limit
    else:
        section_179_deduction = section_179_total
        section_179_carryover = 0

    # Calculate total deduction
    total_deduction = section_179_deduction + depreciation_total

    # Return report data
    return {
        'tax_year': tax_year,
        'section_179_items': section_179_items,
        'depreciation_items': depreciation_items,
        'section_179_total': section_179_total,
        'section_179_limit': section_179_limit,
        'section_179_deduction': section_179_deduction,
        'section_179_carryover': section_179_carryover,
        'depreciation_total': depreciation_total,
        'total_deduction': total_deduction
    }

def generate_depreciation_schedule(tax_item_id: int, years: int = 10) -> List[Dict]:
    """
    Generate a depreciation schedule for a specific tax item.

    Args:
        tax_item_id: ID of the tax item
        years: Number of years to project

    Returns:
        List of yearly depreciation amounts
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM tax_items WHERE id = ?", (tax_item_id,))
    item = dict(cursor.fetchone())
    conn.close()

    purchase_year = int(item['purchase_date'].split('-')[0])
    business_amount = item['amount'] * (item['business_use_percentage'] / 100)

    schedule = []

    for year in range(purchase_year, purchase_year + years):
        if item['use_section_179'] and year == purchase_year:
            # Section 179 deduction in first year
            depreciation = business_amount
            remaining = 0
        else:
            # Regular depreciation
            depreciation = calculate_depreciation(
                business_amount,
                item['depreciation_years'],
                purchase_year,
                year
            )

            # Calculate remaining value
            prior_years = list(range(purchase_year, year))
            prior_depreciation = sum(
                calculate_depreciation(business_amount, item['depreciation_years'], purchase_year, y)
                for y in prior_years
            )

            total_depreciation = prior_depreciation + depreciation
            remaining = business_amount - total_depreciation

        schedule.append({
            'year': year,
            'depreciation': depreciation,
            'remaining': max(0, remaining)
        })

        # Stop if fully depreciated
        if remaining <= 0:
            break

    return schedule
