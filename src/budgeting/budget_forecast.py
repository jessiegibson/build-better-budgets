"""
Budget and Forecasting Module

Provides functionality for creating and managing budgets, tracking goals,
and forecasting future expenses based on historical data.
"""

import os
import sqlite3
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union
from calendar import monthrange

# Import local modules
from data_ingestion import get_db_connection

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Budget:
    """Class for managing budgets and comparing to actual spending."""

    def __init__(self, budget_id: Optional[int] = None):
        """
        Initialize a budget, optionally loading an existing one.

        Args:
            budget_id: ID of an existing budget to load (optional)
        """
        self.id = budget_id
        self.name = ""
        self.start_date = None
        self.end_date = None
        self.total_amount = 0.0
        self.notes = ""
        self.categories = {}  # Map category names to budget amounts

        if budget_id is not None:
            self.load_budget(budget_id)

    def load_budget(self, budget_id: int) -> bool:
        """
        Load an existing budget from the database.

        Args:
            budget_id: ID of the budget to load

        Returns:
            True if the budget was found and loaded, False otherwise
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        # Load budget details
        cursor.execute("""
            SELECT name, start_date, end_date, total_amount, notes
            FROM budgets
            WHERE id = ?
        """, (budget_id,))

        budget = cursor.fetchone()
        if not budget:
            conn.close()
            return False

        self.id = budget_id
        self.name = budget['name']
        self.start_date = budget['start_date']
        self.end_date = budget['end_date']
        self.total_amount = budget['total_amount']
        self.notes = budget['notes']

        # Load budget categories
        cursor.execute("""
            SELECT category, amount
            FROM budget_categories
            WHERE budget_id = ?
        """, (budget_id,))

        categories = cursor.fetchall()
        self.categories = {cat['category']: cat['amount'] for cat in categories}

        conn.close()
        return True

    def save(self) -> int:
        """
        Save the budget to the database.

        Returns:
            ID of the saved budget
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        if self.id is None:
            # Create new budget
            cursor.execute("""
                INSERT INTO budgets (name, start_date, end_date, total_amount, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (
                self.name,
                self.start_date,
                self.end_date,
                self.total_amount,
                self.notes
            ))

            self.id = cursor.lastrowid

            # Add budget categories
            for category, amount in self.categories.items():
                cursor.execute("""
                    INSERT INTO budget_categories (budget_id, category, amount)
                    VALUES (?, ?, ?)
                """, (self.id, category, amount))
        else:
            # Update existing budget
            cursor.execute("""
                UPDATE budgets
                SET name = ?, start_date = ?, end_date = ?, total_amount = ?, notes = ?
                WHERE id = ?
            """, (
                self.name,
                self.start_date,
                self.end_date,
                self.total_amount,
                self.notes,
                self.id
            ))

            # Delete existing categories
            cursor.execute("DELETE FROM budget_categories WHERE budget_id = ?", (self.id,))

            # Add updated categories
            for category, amount in self.categories.items():
                cursor.execute("""
                    INSERT INTO budget_categories (budget_id, category, amount)
                    VALUES (?, ?, ?)
                """, (self.id, category, amount))

        conn.commit()
        conn.close()

        return self.id

    def delete(self) -> bool:
        """
        Delete the budget from the database.

        Returns:
            True if the budget was deleted, False otherwise
        """
        if self.id is None:
            return False

        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete budget categories
        cursor.execute("DELETE FROM budget_categories WHERE budget_id = ?", (self.id,))

        # Delete budget
        cursor.execute("DELETE FROM budgets WHERE id = ?", (self.id,))

        conn.commit()
        conn.close()

        self.id = None
        return True

    def set_category_amount(self, category: str, amount: float) -> None:
        """
        Set the budget amount for a category.

        Args:
            category: Category name
            amount: Budget amount
        """
        self.categories[category] = amount
        self.total_amount = sum(self.categories.values())

    def get_actual_spending(self) -> Dict[str, float]:
        """
        Get actual spending by category for the budget period.

        Returns:
            Dictionary mapping categories to actual spending amounts
        """
        if self.start_date is None or self.end_date is None:
            return {}

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get spending by category
        cursor.execute("""
            SELECT expense_category, SUM(amount) as total
            FROM consolidated_transactions
            WHERE date_posted BETWEEN ? AND ?
                AND expense_category IS NOT NULL
                AND expense_category != ''
                AND amount < 0
            GROUP BY expense_category
        """, (self.start_date, self.end_date))

        results = cursor.fetchall()
        spending = {row['expense_category']: abs(row['total']) for row in results}

        conn.close()

        return spending

    def get_budget_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the budget with actual spending comparison.

        Returns:
            Dictionary with budget details and spending comparison
        """
        actual_spending = self.get_actual_spending()

        # Calculate total actual spending
        total_spent = sum(actual_spending.values())

        # Calculate remaining amount and percentage
        remaining = self.total_amount - total_spent
        if self.total_amount > 0:
            percent_used = (total_spent / self.total_amount) * 100
        else:
            percent_used = 0

        # Compare by category
        categories = []
        for category, budgeted in self.categories.items():
            spent = actual_spending.get(category, 0)
            remaining_cat = budgeted - spent
            if budgeted > 0:
                percent_used_cat = (spent / budgeted) * 100
            else:
                percent_used_cat = 0

            categories.append({
                'category': category,
                'budgeted': budgeted,
                'spent': spent,
                'remaining': remaining_cat,
                'percent_used': percent_used_cat
            })

        # Add categories with spending but no budget
        for category, spent in actual_spending.items():
            if category not in self.categories:
                categories.append({
                    'category': category,
                    'budgeted': 0,
                    'spent': spent,
                    'remaining': -spent,
                    'percent_used': float('inf')
                })

        # Sort categories by percentage used
        categories.sort(key=lambda x: x['percent_used'], reverse=True)

        return {
            'id': self.id,
            'name': self.name,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'total_budgeted': self.total_amount,
            'total_spent': total_spent,
            'remaining': remaining,
            'percent_used': percent_used,
            'categories': categories
        }

class Goal:
    """Class for managing financial goals."""

    def __init__(self, goal_id: Optional[int] = None):
        """
        Initialize a goal, optionally loading an existing one.

        Args:
            goal_id: ID of an existing goal to load (optional)
        """
        self.id = goal_id
        self.name = ""
        self.target_amount = 0.0
        self.current_amount = 0.0
        self.start_date = None
        self.target_date = None
        self.category = None
        self.notes = ""

        if goal_id is not None:
            self.load_goal(goal_id)

    def load_goal(self, goal_id: int) -> bool:
        """
        Load an existing goal from the database.

        Args:
            goal_id: ID of the goal to load

        Returns:
            True if the goal was found and loaded, False otherwise
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        # Load goal details
        cursor.execute("""
            SELECT name, target_amount, current_amount, start_date, target_date, category, notes
            FROM goals
            WHERE id = ?
        """, (goal_id,))

        goal = cursor.fetchone()
        if not goal:
            conn.close()
            return False

        self.id = goal_id
        self.name = goal['name']
        self.target_amount = goal['target_amount']
        self.current_amount = goal['current_amount']
        self.start_date = goal['start_date']
        self.target_date = goal['target_date']
        self.category = goal['category']
        self.notes = goal['notes']

        conn.close()
        return True

    def save(self) -> int:
        """
        Save the goal to the database.

        Returns:
            ID of the saved goal
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        if self.id is None:
            # Create new goal
            cursor.execute("""
                INSERT INTO goals (name, target_amount, current_amount, start_date, target_date, category, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                self.name,
                self.target_amount,
                self.current_amount,
                self.start_date,
                self.target_date,
                self.category,
                self.notes
            ))

            self.id = cursor.lastrowid
        else:
            # Update existing goal
            cursor.execute("""
                UPDATE goals
                SET name = ?, target_amount = ?, current_amount = ?, start_date = ?, target_date = ?, category = ?, notes = ?
                WHERE id = ?
            """, (
                self.name,
                self.target_amount,
                self.current_amount,
                self.start_date,
                self.target_date,
                self.category,
                self.notes,
                self.id
            ))

        conn.commit()
        conn.close()

        return self.id

    def delete(self) -> bool:
        """
        Delete the goal from the database.

        Returns:
            True if the goal was deleted, False otherwise
        """
        if self.id is None:
            return False

        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete goal transactions
        cursor.execute("DELETE FROM goal_transactions WHERE goal_id = ?", (self.id,))

        # Delete goal
        cursor.execute("DELETE FROM goals WHERE id = ?", (self.id,))

        conn.commit()
        conn.close()

        self.id = None
        return True

    def add_transaction(self, amount: float, date: Optional[str] = None, notes: str = "") -> int:
        """
        Add a transaction for this goal.

        Args:
            amount: Transaction amount
            date: Transaction date (default: today)
            notes: Transaction notes

        Returns:
            ID of the created transaction
        """
        if self.id is None:
            raise ValueError("Goal must be saved before adding transactions")

        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Add transaction
        cursor.execute("""
            INSERT INTO goal_transactions (goal_id, amount, date, notes)
            VALUES (?, ?, ?, ?)
        """, (self.id, amount, date, notes))

        transaction_id = cursor.lastrowid

        # Update current amount
        self.current_amount += amount
        cursor.execute("""
            UPDATE goals
            SET current_amount = ?
            WHERE id = ?
        """, (self.current_amount, self.id))

        conn.commit()
        conn.close()

        return transaction_id

    def get_transactions(self) -> List[Dict[str, Any]]:
        """
        Get all transactions for this goal.

        Returns:
            List of transaction dictionaries
        """
        if self.id is None:
            return []

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, amount, date, notes
            FROM goal_transactions
            WHERE goal_id = ?
            ORDER BY date DESC
        """, (self.id,))

        transactions = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return transactions

    def get_progress(self) -> Dict[str, Any]:
        """
        Get progress details for this goal.

        Returns:
            Dictionary with progress information
        """
        progress = {}

        # Calculate basic progress
        if self.target_amount > 0:
            progress['percent_complete'] = (self.current_amount / self.target_amount) * 100
        else:
            progress['percent_complete'] = 0

        progress['remaining'] = self.target_amount - self.current_amount

        # Calculate time-based progress
        if self.start_date and self.target_date:
            start = datetime.strptime(self.start_date, '%Y-%m-%d')
            target = datetime.strptime(self.target_date, '%Y-%m-%d')
            today = datetime.now()

            total_days = (target - start).days
            elapsed_days = (today - start).days

            if total_days > 0:
                progress['percent_time_elapsed'] = min(100, max(0, (elapsed_days / total_days) * 100))

                # Calculate whether on track
                expected_progress = (elapsed_days / total_days) * self.target_amount
                progress['on_track'] = self.current_amount >= expected_progress

                # Calculate required contribution to reach goal
                remaining_days = max(1, (target - today).days)
                progress['required_daily'] = progress['remaining'] / remaining_days

                # Calculate monthly requirement
                progress['required_monthly'] = progress['required_daily'] * 30
            else:
                progress['percent_time_elapsed'] = 100
                progress['on_track'] = False
                progress['required_daily'] = progress['remaining']
                progress['required_monthly'] = progress['remaining']
        else:
            progress['percent_time_elapsed'] = None
            progress['on_track'] = None
            progress['required_daily'] = None
            progress['required_monthly'] = None

        return progress

def get_all_budgets() -> List[Dict[str, Any]]:
    """
    Get a list of all budgets.

    Returns:
        List of budget summary dictionaries
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, start_date, end_date, total_amount
        FROM budgets
        ORDER BY start_date DESC
    """)

    budgets = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Add status information
    for budget in budgets:
        # Determine if current, past, or future
        today = datetime.now().strftime('%Y-%m-%d')
        if budget['start_date'] <= today <= budget['end_date']:
            budget['status'] = 'current'
        elif today < budget['start_date']:
            budget['status'] = 'future'
        else:
            budget['status'] = 'past'

    return budgets

def get_all_goals() -> List[Dict[str, Any]]:
    """
    Get a list of all goals.

    Returns:
        List of goal dictionaries with progress information
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, target_amount, current_amount, start_date, target_date, category
        FROM goals
        ORDER BY target_date
    """)

    goals = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Add progress information
    for goal in goals:
        g = Goal(goal['id'])
        progress = g.get_progress()
        goal.update(progress)

    return goals

def create_monthly_budget(year: int, month: int, template_id: Optional[int] = None) -> int:
    """
    Create a monthly budget, optionally based on a template.

    Args:
        year: Year for the budget
        month: Month for the budget (1-12)
        template_id: ID of a template budget to use (optional)

    Returns:
        ID of the created budget
    """
    # Validate month
    if month < 1 or month > 12:
        raise ValueError("Month must be between 1 and 12")

    # Calculate start and end dates
    start_date = datetime(year, month, 1)
    _, last_day = monthrange(year, month)
    end_date = datetime(year, month, last_day)

    # Format dates as strings
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    # Create budget
    budget = Budget()
    budget.name = f"Budget for {start_date.strftime('%B %Y')}"
    budget.start_date = start_str
    budget.end_date = end_str

    # If using a template, copy categories from template
    if template_id is not None:
        template = Budget(template_id)
        budget.categories = template.categories.copy()
        budget.total_amount = template.total_amount
        budget.notes = f"Based on template: {template.name}"
    else:
        # Otherwise, use historical data for the same month in the previous year
        prev_year = year - 1
        prev_start = datetime(prev_year, month, 1)
        _, prev_last = monthrange(prev_year, month)
        prev_end = datetime(prev_year, month, prev_last)

        prev_start_str = prev_start.strftime('%Y-%m-%d')
        prev_end_str = prev_end.strftime('%Y-%m-%d')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get historical spending by category
        cursor.execute("""
            SELECT expense_category, SUM(amount) as total
            FROM consolidated_transactions
            WHERE date_posted BETWEEN ? AND ?
                AND expense_category IS NOT NULL
                AND expense_category != ''
                AND amount < 0
            GROUP BY expense_category
        """, (prev_start_str, prev_end_str))

        results = cursor.fetchall()
        conn.close()

        # Use historical spending as budget amounts
        for row in results:
            category = row['expense_category']
            amount = abs(row['total'])
            budget.set_category_amount(category, amount)

        budget.notes = f"Based on historical spending for {prev_start.strftime('%B %Y')}"

    # Save the budget
    budget_id = budget.save()
    return budget_id

def forecast_expenses(months: int = 3) -> Dict[str, List[Dict[str, Any]]]:
    """
    Forecast expenses for the next several months.

    Args:
        months: Number of months to forecast

    Returns:
        Dictionary mapping month keys to lists of forecasted expenses
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get recurring expenses
    cursor.execute("""
        SELECT description, amount, frequency, next_date, category, source, notes
        FROM recurring_forecasts
        ORDER BY ABS(amount) DESC
    """)

    recurring = [dict(row) for row in cursor.fetchall()]

    # Get recurring transactions from the database as well
    cursor.execute("""
        SELECT
            id,
            description,
            AVG(amount) as avg_amount,
            expense_category,
            recurring_freq,
            MAX(date_posted) as latest_date,
            source
        FROM consolidated_transactions
        WHERE recurring = 1
        GROUP BY recurring_group
        ORDER BY MAX(date_posted) DESC
    """)

    recurring_trans = [dict(row) for row in cursor.fetchall()]

    # Combine the two sources
    for trans in recurring_trans:
        # Check if this transaction is already in recurring_forecasts
        existing = any(r['description'] == trans['description'] and
                      abs(r['amount'] - trans['avg_amount']) < 0.01
                      for r in recurring)

        if not existing:
            # Calculate next date based on frequency and latest date
            latest_date = datetime.strptime(trans['latest_date'], '%Y-%m-%d')
            frequency = trans['recurring_freq']

            if frequency == "WEEKLY":
                next_date = latest_date + timedelta(days=7)
            elif frequency == "MONTHLY":
                month = latest_date.month + 1
                year = latest_date.year
                if month > 12:
                    month = 1
                    year += 1
                next_date = datetime(year, month, min(latest_date.day, monthrange(year, month)[1]))
            elif frequency == "QUARTERLY":
                month = latest_date.month + 3
                year = latest_date.year
                if month > 12:
                    month = month - 12
                    year += 1
                next_date = datetime(year, month, min(latest_date.day, monthrange(year, month)[1]))
            elif frequency == "YEARLY":
                next_date = datetime(latest_date.year + 1, latest_date.month, latest_date.day)
            else:
                # Default to monthly
                month = latest_date.month + 1
                year = latest_date.year
                if month > 12:
                    month = 1
                    year += 1
                next_date = datetime(year, month, min(latest_date.day, monthrange(year, month)[1]))

            # Add to recurring list
            recurring.append({
                'description': trans['description'],
                'amount': trans['avg_amount'],
                'frequency': frequency,
                'next_date': next_date.strftime('%Y-%m-%d'),
                'category': trans['expense_category'],
                'source': trans['source'],
                'notes': f"Based on historical transactions"
            })

    # Generate forecast for each month
    today = datetime.now()
    forecast = {}

    for i in range(months):
        # Calculate month
        forecast_date = today.replace(day=1) + timedelta(days=32 * i)
        forecast_date = forecast_date.replace(day=1)  # First day of month

        # End of month
        _, last_day = monthrange(forecast_date.year, forecast_date.month)
        month_end = forecast_date.replace(day=last_day)

        # Format as string key
        month_key = forecast_date.strftime('%Y-%m')

        # Calculate expected expenses for this month
        month_expenses = []

        for expense in recurring:
            next_date = datetime.strptime(expense['next_date'], '%Y-%m-%d')
            frequency = expense['frequency']

            # Determine if this expense falls in the current forecast month
            expense_in_month = False

            # Copy of next_date for iteration
            check_date = next_date

            # Check a reasonable number of iterations (12 should be enough for any frequency)
            for _ in range(12):
                if forecast_date <= check_date <= month_end:
                    expense_in_month = True
                    break

                # Move to next occurrence based on frequency
                if frequency == "WEEKLY":
                    check_date = check_date + timedelta(days=7)
                elif frequency == "MONTHLY":
                    month = check_date.month + 1
                    year = check_date.year
                    if month > 12:
                        month = 1
                        year += 1
                    check_date = check_date.replace(year=year, month=month)
                elif frequency == "QUARTERLY":
                    month = check_date.month + 3
                    year = check_date.year
                    if month > 12:
                        month = month - 12
                        year += 1
                    check_date = check_date.replace(year=year, month=month)
                elif frequency == "YEARLY":
                    check_date = check_date.replace(year=check_date.year + 1)
                else:
                    # If unknown frequency, assume not recurring
                    break

            if expense_in_month:
                month_expenses.append({
                    'description': expense['description'],
                    'amount': expense['amount'],
                    'date': check_date.strftime('%Y-%m-%d'),
                    'category': expense['category'],
                    'frequency': frequency,
                    'notes': expense['notes']
                })

        # Sort by date
        month_expenses.sort(key=lambda x: x['date'])
        forecast[month_key] = month_expenses

    conn.close()
    return forecast

def get_spending_patterns() -> Dict[str, Any]:
    """
    Analyze spending patterns for insights.

    Returns:
        Dictionary with spending pattern insights
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get spending by month for the past year
    cursor.execute("""
        SELECT
            strftime('%Y-%m', date_posted) as month,
            SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as spending,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income
        FROM consolidated_transactions
        WHERE date_posted >= date('now', '-12 months')
        GROUP BY month
        ORDER BY month
    """)

    monthly = [dict(row) for row in cursor.fetchall()]

    # Get spending by category for the past year
    cursor.execute("""
        SELECT
            expense_category,
            COUNT(*) as count,
            SUM(amount) as total,
            AVG(amount) as average,
            MIN(amount) as minimum,
            MAX(amount) as maximum
        FROM consolidated_transactions
        WHERE date_posted >= date('now', '-12 months')
            AND expense_category IS NOT NULL
            AND expense_category != ''
            AND amount < 0
        GROUP BY expense_category
        ORDER BY SUM(amount)
    """)

    categories = [dict(row) for row in cursor.fetchall()]

    # Calculate monthly averages and variance
    spending_vals = [abs(row['spending']) for row in monthly]
    if spending_vals:
        avg_spending = sum(spending_vals) / len(spending_vals)
        variance = sum((x - avg_spending) ** 2 for x in spending_vals) / len(spending_vals)
        std_dev = variance ** 0.5
        cov = std_dev / avg_spending if avg_spending > 0 else 0
    else:
        avg_spending = 0
        std_dev = 0
        cov = 0

    # Calculate monthly net savings rate
    for month in monthly:
        month['net'] = month['income'] + month['spending']  # spending is negative
        if month['income'] > 0:
            month['savings_rate'] = month['net'] / month['income'] * 100
        else:
            month['savings_rate'] = 0

    # Calculate average savings rate
    savings_rates = [m['savings_rate'] for m in monthly]
    avg_savings_rate = sum(savings_rates) / len(savings_rates) if savings_rates else 0

    # Calculate trend
    if len(spending_vals) >= 2:
        trend = spending_vals[-1] - spending_vals[0]
        trend_pct = trend / spending_vals[0] * 100 if spending_vals[0] > 0 else 0
    else:
        trend = 0
        trend_pct = 0

    # Identify top expense categories
    top_categories = sorted(categories, key=lambda x: abs(x['total']))[-5:]
    top_categories.reverse()  # Highest first

    # Identify volatile categories (high COV)
    volatile_categories = []
    for cat in categories:
        if cat['count'] >= 3:  # Need at least 3 transactions for meaningful stats
            cat_cov = abs(cat['average'] / cat['total']) if cat['total'] != 0 else 0
            if cat_cov > 0.5:  # Arbitrary threshold
                volatile_categories.append({
                    'category': cat['expense_category'],
                    'variability': cat_cov,
                    'total': cat['total'],
                    'average': cat['average'],
                    'count': cat['count']
                })

    # Sort by variability
    volatile_categories.sort(key=lambda x: x['variability'], reverse=True)

    conn.close()

    return {
        'monthly_data': monthly,
        'avg_monthly_spending': avg_spending,
        'spending_std_dev': std_dev,
        'spending_cov': cov,
        'avg_savings_rate': avg_savings_rate,
        'trend': trend,
        'trend_percent': trend_pct,
        'top_categories': top_categories,
        'volatile_categories': volatile_categories[:5]  # Top 5 most volatile
    }

if __name__ == "__main__":
    print("Budget and Forecasting Module")

    # Example: Create a monthly budget
    today = datetime.now()
    print(f"\nCreating budget for {today.strftime('%B %Y')}...")
    budget_id = create_monthly_budget(today.year, today.month)
    print(f"Created budget with ID: {budget_id}")

    # Example: Create a goal
    print("\nCreating a sample goal...")
    goal = Goal()
    goal.name = "Emergency Fund"
    goal.target_amount = 10000.0
    goal.current_amount = 2500.0
    goal.start_date = datetime.now().strftime('%Y-%m-%d')
    goal.target_date = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
    goal.category = "Savings"
    goal.notes = "3-6 months of expenses"
    goal_id = goal.save()
    print(f"Created goal with ID: {goal_id}")

    # Example: Get spending patterns
    print("\nAnalyzing spending patterns...")
    patterns = get_spending_patterns()
    print(f"Average monthly spending: ${patterns['avg_monthly_spending']:.2f}")
    print(f"Average savings rate: {patterns['avg_savings_rate']:.1f}%")
    print("Top spending categories:")
    for cat in patterns['top_categories']:
        print(f"  - {cat['expense_category']}: ${abs(cat['total']):.2f}")

    # Example: Forecast expenses
    print("\nForecasting expenses for the next 3 months...")
    forecast = forecast_expenses(3)
    for month, expenses in forecast.items():
        month_date = datetime.strptime(month, '%Y-%m')
        month_name = month_date.strftime('%B %Y')
        total = sum(abs(e['amount']) for e in expenses)
        print(f"  - {month_name}: ${total:.2f} ({len(expenses)} expenses)")
