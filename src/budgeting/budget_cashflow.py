import os
import sys
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any, Union

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
