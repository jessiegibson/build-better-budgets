import os
import sqlite3
import pandas as pd
import datetime
from typing import Dict, List, Any, Optional, Tuple

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json

# Import needed functions from app.py
from app import (
    DB_PATH, MODEL_DIR, 
    initialize_database,
    show_budgets, create_budget, compare_budget_vs_actual,
    show_goals, add_goal, update_goal_progress,
    categorize_transactions, analyze_spending_patterns,
    show_cash_flow_forecast, train_category_classifier,
    # Tax-related functions
    get_tax_items, get_equipment_transactions, add_tax_item, update_tax_item, 
    delete_tax_item, generate_tax_report, generate_depreciation_schedule,
    get_section_179_limit, calculate_depreciation
)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For flash messages and session

# Ensure the necessary directories exist
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), 'static'), exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), 'templates'), exist_ok=True)

# ----------------------
# Data Access Functions
# ----------------------

def get_db_connection():
    """Create a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # This enables column access by name
    return conn

def get_transactions(limit=100, offset=0, filters=None):
    """
    Get transactions from the database with optional filtering.
    
    Args:
        limit: Maximum number of transactions to return
        offset: Number of transactions to skip
        filters: Dict of filters to apply (e.g., {'category': 'groceries'})
        
    Returns:
        List of transaction dictionaries
    """
    conn = get_db_connection()
    
    # Start building the query
    query = """
    SELECT * FROM consolidated_transactions
    """
    
    # Add WHERE clause for filters
    params = []
    if filters:
        where_clauses = []
        for key, value in filters.items():
            if key == 'min_date':
                where_clauses.append("date_posted >= ?")
                params.append(value)
            elif key == 'max_date':
                where_clauses.append("date_posted <= ?")
                params.append(value)
            elif key == 'min_amount':
                where_clauses.append("amount >= ?")
                params.append(float(value))
            elif key == 'max_amount':
                where_clauses.append("amount <= ?")
                params.append(float(value))
            elif key == 'category':
                where_clauses.append("category = ?")
                params.append(value)
            elif key == 'description':
                where_clauses.append("description LIKE ?")
                params.append(f"%{value}%")
            elif key == 'source':
                where_clauses.append("source = ?")
                params.append(value)
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
    
    # Add ORDER BY and LIMIT
    query += " ORDER BY date_posted DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    # Execute the query
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        transactions = [dict(tx) for tx in cursor.fetchall()]
        
        # Ensure amount is a float
        for tx in transactions:
            if 'amount' in tx:
                try:
                    tx['amount'] = float(tx['amount'])
                except (ValueError, TypeError):
                    tx['amount'] = 0.0
        
        conn.close()
        return transactions
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.close()
        return []

def get_transaction_stats():
    """Get statistics about transactions for dashboard."""
    conn = get_db_connection()
    stats = {}
    
    try:
        # Total number of transactions
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM consolidated_transactions")
        stats['total_transactions'] = cursor.fetchone()[0]
        
        # Total spend (negative amounts)
        cursor.execute("SELECT SUM(amount) FROM consolidated_transactions WHERE amount < 0")
        spend = cursor.fetchone()[0]
        stats['total_spend'] = abs(spend) if spend else 0
        
        # Total income (positive amounts)
        cursor.execute("SELECT SUM(amount) FROM consolidated_transactions WHERE amount > 0")
        income = cursor.fetchone()[0]
        stats['total_income'] = income if income else 0
        
        # Date range
        cursor.execute("SELECT MIN(date_posted), MAX(date_posted) FROM consolidated_transactions")
        min_date, max_date = cursor.fetchone()
        stats['date_range'] = f"{min_date} to {max_date}"
        
        # Category counts
        cursor.execute("""
        SELECT category, COUNT(*) as count 
        FROM consolidated_transactions 
        WHERE category IS NOT NULL AND category != '' 
        GROUP BY category 
        ORDER BY count DESC 
        LIMIT 5
        """)
        stats['top_categories'] = dict(cursor.fetchall())
        
        # Account/source counts
        cursor.execute("""
        SELECT source, COUNT(*) as count 
        FROM consolidated_transactions 
        GROUP BY source 
        ORDER BY count DESC
        """)
        stats['sources'] = dict(cursor.fetchall())
        
        conn.close()
        return stats
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.close()
        return {'error': str(e)}

def get_monthly_spending_chart():
    """Generate monthly spending and income chart data."""
    conn = get_db_connection()
    
    try:
        # Get spending and income by month
        cursor = conn.cursor()
        cursor.execute("""
        SELECT 
            strftime('%Y-%m', date_posted) as month,
            SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as expenses,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income
        FROM consolidated_transactions
        GROUP BY strftime('%Y-%m', date_posted)
        ORDER BY month ASC
        """)
        
        months = []
        expenses = []
        incomes = []
        
        for row in cursor.fetchall():
            months.append(row['month'])
            expenses.append(abs(row['expenses'] or 0))
            incomes.append(row['income'] or 0)
        
        # Create a bar chart
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=months,
            y=expenses,
            name='Expenses',
            marker_color='indianred'
        ))
        fig.add_trace(go.Bar(
            x=months,
            y=incomes,
            name='Income',
            marker_color='lightseagreen'
        ))
        
        # Add a net savings line
        net = [inc - exp for inc, exp in zip(incomes, expenses)]
        fig.add_trace(go.Scatter(
            x=months,
            y=net,
            name='Net',
            line=dict(color='royalblue', width=3)
        ))
        
        fig.update_layout(
            title='Monthly Income and Expenses',
            xaxis_title='Month',
            yaxis_title='Amount ($)',
            barmode='group',
            template='plotly_white'
        )
        
        conn.close()
        return fig.to_json()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.close()
        return None

def get_category_breakdown_chart():
    """Generate pie chart of spending by category."""
    conn = get_db_connection()
    
    try:
        # Get spending by category
        cursor = conn.cursor()
        cursor.execute("""
        SELECT 
            COALESCE(category, 'Uncategorized') as category,
            SUM(ABS(amount)) as total
        FROM consolidated_transactions
        WHERE amount < 0
        GROUP BY COALESCE(category, 'Uncategorized')
        ORDER BY total DESC
        LIMIT 10
        """)
        
        categories = []
        totals = []
        
        for row in cursor.fetchall():
            categories.append(row['category'])
            totals.append(row['total'])
        
        # Create a pie chart
        fig = go.Figure(data=[go.Pie(
            labels=categories,
            values=totals,
            hole=.3,
            textinfo='label+percent',
            insidetextorientation='radial'
        )])
        
        fig.update_layout(
            title='Spending by Category',
            template='plotly_white'
        )
        
        conn.close()
        return fig.to_json()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.close()
        return None

def get_budget_comparison_chart(budget_id=None):
    """Generate chart comparing budget to actual spending."""
    conn = get_db_connection()
    
    try:
        # If no budget ID is provided, get the most recent budget
        if budget_id is None:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id FROM budgets 
            ORDER BY start_date DESC 
            LIMIT 1
            """)
            result = cursor.fetchone()
            if result:
                budget_id = result['id']
            else:
                return None  # No budgets found
        
        # Get budget details
        cursor = conn.cursor()
        cursor.execute("""
        SELECT name, start_date, end_date 
        FROM budgets 
        WHERE id = ?
        """, (budget_id,))
        budget = cursor.fetchone()
        
        if not budget:
            return None
        
        # Get budget categories and amounts
        cursor.execute("""
        SELECT category, amount 
        FROM budget_categories 
        WHERE budget_id = ?
        """, (budget_id,))
        
        budget_data = {}
        for row in cursor.fetchall():
            budget_data[row['category']] = row['amount']
        
        # Get actual spending for each category
        actual_data = {}
        for category in budget_data.keys():
            cursor.execute("""
            SELECT SUM(amount) as actual
            FROM consolidated_transactions
            WHERE category = ? AND date_posted BETWEEN ? AND ?
            """, (category, budget['start_date'], budget['end_date']))
            result = cursor.fetchone()
            actual_amount = abs(result['actual'] or 0)
            actual_data[category] = actual_amount
        
        # Create a bar chart comparison
        categories = list(budget_data.keys())
        budget_amounts = [budget_data[cat] for cat in categories]
        actual_amounts = [actual_data[cat] for cat in categories]
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=categories,
            y=budget_amounts,
            name='Budget',
            marker_color='lightseagreen'
        ))
        fig.add_trace(go.Bar(
            x=categories,
            y=actual_amounts,
            name='Actual',
            marker_color='indianred'
        ))
        
        fig.update_layout(
            title=f'Budget vs. Actual: {budget["name"]}',
            xaxis_title='Category',
            yaxis_title='Amount ($)',
            barmode='group',
            template='plotly_white'
        )
        
        conn.close()
        return fig.to_json()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.close()
        return None

def get_goals_progress_chart():
    """Generate progress chart for financial goals."""
    conn = get_db_connection()
    
    try:
        # Get all active goals
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, name, type, target_amount, current_amount, start_date, target_date
        FROM goals
        WHERE target_amount > current_amount  -- Only show incomplete goals
        ORDER BY target_date ASC
        """)
        
        goals = cursor.fetchall()
        
        if not goals:
            return None
        
        names = []
        progress = []
        remaining = []
        
        for goal in goals:
            names.append(goal['name'])
            current = goal['current_amount']
            target = goal['target_amount']
            progress.append((current / target) * 100)
            remaining.append(100 - (current / target) * 100)
        
        # Create a stacked bar chart for progress
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            y=names,
            x=progress,
            name='Progress',
            orientation='h',
            marker=dict(color='lightseagreen')
        ))
        
        fig.add_trace(go.Bar(
            y=names,
            x=remaining,
            name='Remaining',
            orientation='h',
            marker=dict(color='lightgray')
        ))
        
        fig.update_layout(
            title='Financial Goals Progress',
            xaxis_title='Percent Complete',
            yaxis_title='Goal',
            barmode='stack',
            template='plotly_white'
        )
        
        conn.close()
        return fig.to_json()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.close()
        return None

# ----------------------
# Flask Route Handlers
# ----------------------

@app.route('/')
def index():
    """Dashboard home page."""
    # Get transaction stats for dashboard
    stats = get_transaction_stats()
    
    # Get chart data
    monthly_chart = get_monthly_spending_chart()
    category_chart = get_category_breakdown_chart()
    budget_chart = get_budget_comparison_chart()
    goals_chart = get_goals_progress_chart()
    
    # Get recent transactions
    recent_transactions = get_transactions(limit=5)
    
    # Ensure all amounts are float for template comparison operations
    for tx in recent_transactions:
        if 'amount' in tx and not isinstance(tx['amount'], float):
            try:
                tx['amount'] = float(tx['amount'])
            except (ValueError, TypeError):
                tx['amount'] = 0.0
    
    return render_template(
        'index.html',
        stats=stats,
        monthly_chart=monthly_chart,
        category_chart=category_chart,
        budget_chart=budget_chart,
        goals_chart=goals_chart,
        recent_transactions=recent_transactions
    )

@app.route('/transactions')
def transactions():
    """Transactions list page with filtering."""
    # Get filter params from query string
    filters = {}
    for key in ['min_date', 'max_date', 'min_amount', 'max_amount', 'category', 'description', 'source']:
        value = request.args.get(key)
        if value:
            filters[key] = value
    
    # Get pagination params
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 50))
    offset = (page - 1) * limit
    
    # Get transactions
    transactions = get_transactions(limit=limit, offset=offset, filters=filters)
    
    # Ensure all amounts are float for template comparison operations
    # (should be handled in get_transactions now, but adding as extra precaution)
    for tx in transactions:
        if 'amount' in tx and not isinstance(tx['amount'], float):
            try:
                tx['amount'] = float(tx['amount'])
            except (ValueError, TypeError):
                tx['amount'] = 0.0
    
    # Get categories and sources for filter dropdowns
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT category FROM consolidated_transactions WHERE category IS NOT NULL AND category != ''")
    categories = [row['category'] for row in cursor.fetchall()]
    
    cursor.execute("SELECT DISTINCT source FROM consolidated_transactions WHERE source IS NOT NULL AND source != ''")
    sources = [row['source'] for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template(
        'transactions.html',
        transactions=transactions,
        categories=categories,
        sources=sources,
        filters=filters,
        page=page,
        limit=limit
    )

@app.route('/transaction/<int:transaction_id>')
def transaction_detail(transaction_id):
    """Transaction detail page."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM consolidated_transactions WHERE id = ?", (transaction_id,))
    transaction = cursor.fetchone()
    
    if not transaction:
        flash("Transaction not found", "error")
        return redirect(url_for('transactions'))
    
    conn.close()
    
    # Convert to dictionary and ensure amount is float
    transaction_dict = dict(transaction)
    if 'amount' in transaction_dict:
        try:
            transaction_dict['amount'] = float(transaction_dict['amount'])
        except (ValueError, TypeError):
            transaction_dict['amount'] = 0.0
    
    return render_template('transaction_detail.html', transaction=transaction_dict)

@app.route('/transaction/<int:transaction_id>/update', methods=['POST'])
def update_transaction(transaction_id):
    """Update transaction details."""
    category = request.form.get('category')
    notes = request.form.get('notes')
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE consolidated_transactions SET category = ?, notes = ? WHERE id = ?",
            (category, notes, transaction_id)
        )
        conn.commit()
        flash("Transaction updated successfully", "success")
    except sqlite3.Error as e:
        conn.rollback()
        flash(f"Error updating transaction: {e}", "error")
    finally:
        conn.close()
    
    return redirect(url_for('transaction_detail', transaction_id=transaction_id))

@app.route('/budgets')
def budgets():
    """Budgets list page with detailed information."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get all budgets
    cursor.execute("""
    SELECT b.id, b.name, b.start_date, b.end_date, b.period,
           SUM(bc.amount) as total_budget
    FROM budgets b
    LEFT JOIN budget_categories bc ON b.id = bc.budget_id
    GROUP BY b.id
    ORDER BY b.start_date DESC
    """)
    
    budgets = []
    current_budget = None
    today = datetime.date.today().isoformat()
    
    for row in cursor.fetchall():
        budget = dict(row)
        
        # Calculate actual spending for this budget period
        cursor.execute("""
        SELECT SUM(amount) as actual_spent
        FROM consolidated_transactions
        WHERE date_posted BETWEEN ? AND ?
        AND amount < 0
        """, (budget['start_date'], budget['end_date']))
        
        result = cursor.fetchone()
        budget['actual_spent'] = abs(result['actual_spent'] or 0)
        budget['remaining'] = budget['total_budget'] - budget['actual_spent']
        budget['percent_used'] = (budget['actual_spent'] / budget['total_budget'] * 100) if budget['total_budget'] > 0 else 0
        
        # Check if this is a current budget (today falls within the date range)
        if budget['start_date'] <= today <= budget['end_date']:
            # If we find multiple current budgets, prioritize the one that starts most recently
            if not current_budget or budget['start_date'] > current_budget['start_date']:
                current_budget = budget
        
        budgets.append(budget)
    
    # If no current budget is found, use the most recent one
    if not current_budget and budgets:
        current_budget = budgets[0]  # The first one is the most recent due to our ORDER BY
    
    # If we have a current budget, get its categories
    if current_budget:
        cursor.execute("""
        SELECT category, amount 
        FROM budget_categories
        WHERE budget_id = ?
        ORDER BY amount DESC
        """, (current_budget['id'],))
        
        categories = []
        for row in cursor.fetchall():
            category = dict(row)
            
            # Get actual spending for this category
            cursor.execute("""
            SELECT SUM(amount) as actual
            FROM consolidated_transactions
            WHERE category = ? 
            AND date_posted BETWEEN ? AND ?
            """, (category['category'], current_budget['start_date'], current_budget['end_date']))
            
            result = cursor.fetchone()
            category['actual'] = abs(result['actual'] or 0)
            category['remaining'] = category['amount'] - category['actual']
            category['percent_used'] = (category['actual'] / category['amount'] * 100) if category['amount'] > 0 else 0
            
            categories.append(category)
        
        current_budget['categories'] = categories
    
    # Generate budget vs actual comparison chart for current budget
    budget_chart = None
    if current_budget and current_budget.get('categories'):
        categories = []
        budget_amounts = []
        actual_amounts = []
        
        for category in current_budget['categories']:
            categories.append(category['category'])
            budget_amounts.append(category['amount'])
            actual_amounts.append(category['actual'])
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=categories,
            y=budget_amounts,
            name='Budget',
            marker_color='lightseagreen'
        ))
        fig.add_trace(go.Bar(
            x=categories,
            y=actual_amounts,
            name='Actual',
            marker_color='indianred'
        ))
        
        fig.update_layout(
            title='Budget vs. Actual Spending',
            xaxis_title='Category',
            yaxis_title='Amount ($)',
            barmode='group',
            template='plotly_white'
        )
        
        budget_chart = fig.to_json()
    
    conn.close()
    
    return render_template(
        'budgets.html', 
        budgets=budgets, 
        current_budget=current_budget,
        budget_chart=budget_chart
    )

@app.route('/budget/<int:budget_id>')
def budget_detail(budget_id):
    """Budget detail page with category breakdown."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get budget details
    cursor.execute("""
    SELECT * FROM budgets WHERE id = ?
    """, (budget_id,))
    
    budget = cursor.fetchone()
    if not budget:
        flash("Budget not found", "error")
        return redirect(url_for('budgets'))
    
    budget = dict(budget)
    
    # Get budget categories
    cursor.execute("""
    SELECT category, amount FROM budget_categories
    WHERE budget_id = ?
    ORDER BY amount DESC
    """, (budget_id,))
    
    categories = []
    for row in cursor.fetchall():
        category = dict(row)
        
        # Get actual spending for this category
        cursor.execute("""
        SELECT SUM(amount) as actual
        FROM consolidated_transactions
        WHERE category = ? 
        AND date_posted BETWEEN ? AND ?
        """, (category['category'], budget['start_date'], budget['end_date']))
        
        result = cursor.fetchone()
        category['actual'] = abs(result['actual'] or 0)
        category['remaining'] = category['amount'] - category['actual']
        category['percent_used'] = (category['actual'] / category['amount'] * 100) if category['amount'] > 0 else 0
        
        categories.append(category)
    
    # Get chart data
    budget_chart = get_budget_comparison_chart(budget_id)
    
    conn.close()
    
    return render_template(
        'budget_detail.html',
        budget=budget,
        categories=categories,
        budget_chart=budget_chart
    )

@app.route('/budget/<int:budget_id>/data')
def get_budget_data(budget_id):
    """API endpoint to get budget data for editing."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get budget details
    cursor.execute("""
    SELECT id, name, start_date, end_date, period
    FROM budgets WHERE id = ?
    """, (budget_id,))
    
    budget = cursor.fetchone()
    if not budget:
        return jsonify({"error": "Budget not found"}), 404
    
    budget_data = dict(budget)
    
    # Get budget categories
    cursor.execute("""
    SELECT category, amount FROM budget_categories
    WHERE budget_id = ?
    ORDER BY amount DESC
    """, (budget_id,))
    
    categories = []
    for row in cursor.fetchall():
        category = dict(row)
        
        # Get actual spending for this category
        cursor.execute("""
        SELECT SUM(amount) as actual
        FROM consolidated_transactions
        WHERE category = ? 
        AND date_posted BETWEEN ? AND ?
        """, (category['category'], budget_data['start_date'], budget_data['end_date']))
        
        result = cursor.fetchone()
        category['actual'] = abs(result['actual'] or 0)
        
        categories.append(category)
    
    budget_data['categories'] = categories
    
    conn.close()
    
    return jsonify(budget_data)

@app.route('/budget/update', methods=['POST'])
def update_budget():
    """Update an existing budget."""
    budget_id = request.form.get('budget_id')
    name = request.form.get('name')
    period = request.form.get('period')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    
    if not budget_id:
        flash("Missing budget ID", "error")
        return redirect(url_for('budgets'))
    
    # Get dynamic category data
    categories = []
    amounts = []
    
    for key, value in request.form.items():
        if key.startswith('category_') and value:
            index = key.split('_')[1]
            amount_key = f'amount_{index}'
            amount = request.form.get(amount_key)
            
            if amount and float(amount) > 0:
                categories.append(value)
                amounts.append(float(amount))
    
    # Update the budget
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Update budget details
        current_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
        UPDATE budgets 
        SET name = ?, start_date = ?, end_date = ?, period = ?, updated_at = ?
        WHERE id = ?
        """, (name, start_date, end_date, period, current_timestamp, budget_id))
        
        # Delete existing categories
        cursor.execute("DELETE FROM budget_categories WHERE budget_id = ?", (budget_id,))
        
        # Add updated budget categories
        for category, amount in zip(categories, amounts):
            cursor.execute("""
            INSERT INTO budget_categories
            (budget_id, category, amount)
            VALUES (?, ?, ?)
            """, (budget_id, category, amount))
        
        conn.commit()
        flash("Budget updated successfully", "success")
    except sqlite3.Error as e:
        conn.rollback()
        flash(f"Error updating budget: {e}", "error")
    finally:
        conn.close()
    
    return redirect(url_for('budgets'))

@app.route('/budget/new', methods=['GET', 'POST'])
def new_budget():
    """Create a new budget with suggestions from recurring expenses."""
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get date range for transaction analysis
        cursor.execute("""
        SELECT MIN(date_posted), MAX(date_posted)
        FROM consolidated_transactions
        """)
        
        date_range = cursor.fetchone()
        min_date, max_date = date_range if date_range else ('N/A', 'N/A')
        
        # Calculate last 3 months for spending analysis
        if max_date != 'N/A':
            max_date_obj = datetime.datetime.strptime(max_date, '%Y-%m-%d')
            three_months_ago = (max_date_obj - datetime.timedelta(days=90)).strftime('%Y-%m-%d')
            date_range_str = f"{three_months_ago} to {max_date}"
        else:
            three_months_ago = 'N/A'
            date_range_str = 'N/A'
        
        # Get monthly spending by category (for history-based suggestions)
        cursor.execute("""
        SELECT category, SUM(amount) as total_spent, COUNT(*) as transaction_count
        FROM consolidated_transactions
        WHERE category IS NOT NULL 
        AND category != ''
        AND date_posted >= ?
        AND amount < 0  -- Only expenses (negative amounts)
        GROUP BY category
        ORDER BY total_spent ASC  -- Ascending because expenses are negative
        """, (three_months_ago,))
        
        top_categories = []
        for row in cursor.fetchall():
            if row['category'] and row['total_spent']:
                top_categories.append({
                    'category': row['category'],
                    'total_spent': abs(row['total_spent']),
                    'transaction_count': row['transaction_count']
                })
        
        # Get recurring expenses for budget suggestions
        cursor.execute("""
        SELECT description, category, AVG(amount) as avg_amount, COUNT(*) as occurrence_count
        FROM consolidated_transactions
        WHERE amount < 0
        AND date_posted >= ?
        GROUP BY category
        HAVING COUNT(*) >= 3 AND category IS NOT NULL AND category != ''
        ORDER BY avg_amount ASC
        """, (three_months_ago,))
        
        recurring_expenses = []
        for row in cursor.fetchall():
            if row['category'] and row['avg_amount']:
                recurring_expenses.append({
                    'category': row['category'],
                    'avg_amount': abs(row['avg_amount']),
                    'occurrence_count': row['occurrence_count']
                })
        
        # Get all existing categories for suggestions
        cursor.execute("""
        SELECT DISTINCT category
        FROM consolidated_transactions
        WHERE category IS NOT NULL AND category != ''
        """)
        
        all_categories = [row['category'] for row in cursor.fetchall()]
        
        # Create suggested budget categories
        suggested_categories = []
        
        # Add recurring expense categories first (most reliable)
        recurring_categories = set()
        for expense in recurring_expenses:
            category = expense['category']
            recurring_categories.add(category)
            suggested_categories.append({
                'category': category,
                'suggested_amount': round(expense['avg_amount'] * 1.1, 2),  # Add 10% buffer
                'recurring_amount': expense['avg_amount'],
                'recurring': True,
                'historical': False
            })
        
        # Add top spending categories that aren't already covered by recurring expenses
        for category in top_categories:
            if category['category'] not in recurring_categories:
                # Calculate monthly average (assuming 3 months of data)
                monthly_avg = category['total_spent'] / 3
                suggested_categories.append({
                    'category': category['category'],
                    'suggested_amount': round(monthly_avg, 2),
                    'historical_amount': monthly_avg,
                    'recurring': False,
                    'historical': True
                })
        
        # Sort by suggested amount (descending)
        suggested_categories.sort(key=lambda x: x['suggested_amount'], reverse=True)
        
        # Build monthly data for chart
        cursor.execute("""
        SELECT 
            strftime('%Y-%m', date_posted) as month,
            SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as expenses,
            SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income
        FROM consolidated_transactions
        GROUP BY strftime('%Y-%m', date_posted)
        ORDER BY month DESC
        LIMIT 6
        """)
        
        monthly_data = []
        for row in cursor.fetchall():
            monthly_data.append({
                'month': row['month'],
                'expenses': row['expenses'] or 0,
                'income': row['income'] or 0
            })
        
        # Reverse to get chronological order
        monthly_data.reverse()
        
        # Create charts
        # Category breakdown chart
        if suggested_categories:
            categories_chart = []
            amounts = []
            for cat in suggested_categories:
                categories_chart.append(cat['category'])
                amounts.append(cat['suggested_amount'])
            
            fig1 = go.Figure(data=[go.Pie(
                labels=categories_chart,
                values=amounts,
                hole=0.4,
                textinfo='label+percent',
                insidetextorientation='radial'
            )])
            
            fig1.update_layout(
                title='Suggested Budget Breakdown',
                margin=dict(t=30, b=0, l=0, r=0),
                showlegend=False
            )
            
            category_chart = fig1.to_json()
        else:
            category_chart = None
        
        # Monthly spending chart
        if monthly_data:
            months = [m['month'] for m in monthly_data]
            expenses = [abs(m['expenses']) for m in monthly_data]
            incomes = [m['income'] for m in monthly_data]
            
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=months,
                y=expenses,
                name='Expenses',
                marker_color='indianred'
            ))
            
            fig2.add_trace(go.Bar(
                x=months,
                y=incomes,
                name='Income',
                marker_color='lightseagreen'
            ))
            
            fig2.update_layout(
                title='Monthly Income and Expenses',
                xaxis_title='Month',
                yaxis_title='Amount ($)',
                barmode='group',
                margin=dict(t=30, b=0, l=0, r=0)
            )
            
            monthly_chart = fig2.to_json()
        else:
            monthly_chart = None
        
        conn.close()
        
        return render_template(
            'new_budget.html',
            suggested_categories=suggested_categories,
            top_categories=top_categories,
            recurring_expenses=recurring_expenses,
            all_categories=all_categories,
            monthly_data=monthly_data,
            date_range=date_range_str,
            category_chart=category_chart,
            monthly_chart=monthly_chart
        )
    
    elif request.method == 'POST':
        # Process form data to create a new budget
        name = request.form.get('name')
        period = request.form.get('period')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        
        # Get dynamic category data
        categories = []
        amounts = []
        
        for key, value in request.form.items():
            if key.startswith('category_') and value:
                index = key.split('_')[1]
                amount_key = f'amount_{index}'
                amount = request.form.get(amount_key)
                
                if amount and float(amount) > 0:
                    categories.append(value)
                    amounts.append(float(amount))
        
        # Create the budget
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Create budget
            current_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
            INSERT INTO budgets 
            (name, start_date, end_date, period, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (name, start_date, end_date, period, current_timestamp, current_timestamp))
            
            budget_id = cursor.lastrowid
            
            # Add budget categories
            for category, amount in zip(categories, amounts):
                cursor.execute("""
                INSERT INTO budget_categories
                (budget_id, category, amount)
                VALUES (?, ?, ?)
                """, (budget_id, category, amount))
            
            conn.commit()
            flash("Budget created successfully", "success")
        except sqlite3.Error as e:
            conn.rollback()
            flash(f"Error creating budget: {e}", "error")
        finally:
            conn.close()
        
        return redirect(url_for('budgets'))

@app.route('/goals')
def goals():
    """Goals list page."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT id, name, type, target_amount, current_amount, start_date, target_date, notes
    FROM goals
    ORDER BY target_date ASC
    """)
    
    goals = []
    for row in cursor.fetchall():
        goal = dict(row)
        
        # Calculate progress percentage
        goal['progress_percent'] = (goal['current_amount'] / goal['target_amount'] * 100) if goal['target_amount'] > 0 else 0
        goal['remaining'] = goal['target_amount'] - goal['current_amount']
        
        # Calculate days left
        today = datetime.date.today().isoformat()
        target_date = datetime.datetime.strptime(goal['target_date'], '%Y-%m-%d').date()
        today_date = datetime.datetime.strptime(today, '%Y-%m-%d').date()
        goal['days_left'] = (target_date - today_date).days
        
        # Get recent transactions
        cursor.execute("""
        SELECT date, amount, notes
        FROM goal_transactions
        WHERE goal_id = ?
        ORDER BY date DESC
        LIMIT 3
        """, (goal['id'],))
        
        goal['recent_transactions'] = [dict(tx) for tx in cursor.fetchall()]
        
        goals.append(goal)
    
    conn.close()
    
    # Get chart data
    goals_chart = get_goals_progress_chart()
    
    return render_template('goals.html', goals=goals, goals_chart=goals_chart)

@app.route('/goal/<int:goal_id>')
def goal_detail(goal_id):
    """Goal detail page with transaction history."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT * FROM goals WHERE id = ?
    """, (goal_id,))
    
    goal = cursor.fetchone()
    if not goal:
        flash("Goal not found", "error")
        return redirect(url_for('goals'))
    
    goal = dict(goal)
    
    # Calculate progress percentage
    goal['progress_percent'] = (goal['current_amount'] / goal['target_amount'] * 100) if goal['target_amount'] > 0 else 0
    goal['remaining'] = goal['target_amount'] - goal['current_amount']
    
    # Calculate days left
    today = datetime.date.today().isoformat()
    target_date = datetime.datetime.strptime(goal['target_date'], '%Y-%m-%d').date()
    today_date = datetime.datetime.strptime(today, '%Y-%m-%d').date()
    goal['days_left'] = (target_date - today_date).days
    
    # Get all transactions for this goal
    cursor.execute("""
    SELECT * FROM goal_transactions
    WHERE goal_id = ?
    ORDER BY date DESC
    """, (goal_id,))
    
    transactions = [dict(tx) for tx in cursor.fetchall()]
    
    # Create progress chart
    if transactions:
        # Convert to pandas for easier manipulation
        df = pd.DataFrame(transactions)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # Calculate cumulative progress
        df['cumulative'] = df['amount'].cumsum()
        
        # Create a line chart
        progress_dates = df['date'].dt.strftime('%Y-%m-%d').tolist()
        progress_amounts = df['cumulative'].tolist()
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=progress_dates,
            y=progress_amounts,
            mode='lines+markers',
            name='Progress',
            line=dict(color='royalblue', width=3)
        ))
        
        # Add target line
        fig.add_shape(
            type="line",
            x0=progress_dates[0],
            y0=0,
            x1=goal['target_date'],
            y1=goal['target_amount'],
            line=dict(color="red", dash="dash")
        )
        
        fig.update_layout(
            title=f'Progress Toward {goal["name"]}',
            xaxis_title='Date',
            yaxis_title='Amount ($)',
            template='plotly_white'
        )
        
        progress_chart = fig.to_json()
    else:
        progress_chart = None
    
    conn.close()
    
    return render_template(
        'goal_detail.html',
        goal=goal,
        transactions=transactions,
        progress_chart=progress_chart
    )

@app.route('/goal/new', methods=['GET', 'POST'])
def new_goal():
    """Create a new financial goal."""
    if request.method == 'GET':
        return render_template('new_goal.html')
    
    elif request.method == 'POST':
        # Process form data to create a new goal
        name = request.form.get('name')
        goal_type = request.form.get('type')
        target_amount = float(request.form.get('target_amount'))
        current_amount = float(request.form.get('current_amount', 0))
        start_date = request.form.get('start_date')
        target_date = request.form.get('target_date')
        notes = request.form.get('notes', '')
        
        # Create the goal
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            current_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
            INSERT INTO goals 
            (name, type, target_amount, current_amount, start_date, target_date, created_at, updated_at, notes)
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
            flash("Goal created successfully", "success")
        except sqlite3.Error as e:
            conn.rollback()
            flash(f"Error creating goal: {e}", "error")
        finally:
            conn.close()
        
        return redirect(url_for('goals'))

@app.route('/goal/<int:goal_id>/update', methods=['POST'])
def update_goal(goal_id):
    """Add a new contribution/update to a goal."""
    amount = float(request.form.get('amount'))
    date = request.form.get('date')
    notes = request.form.get('notes', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Update goal progress
        cursor.execute("""
        UPDATE goals
        SET current_amount = current_amount + ?,
            updated_at = ?
        WHERE id = ?
        """, (amount, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), goal_id))
        
        # Add transaction record
        cursor.execute("""
        INSERT INTO goal_transactions
        (goal_id, amount, date, notes)
        VALUES (?, ?, ?, ?)
        """, (goal_id, amount, date, notes))
        
        conn.commit()
        flash("Goal updated successfully", "success")
    except sqlite3.Error as e:
        conn.rollback()
        flash(f"Error updating goal: {e}", "error")
    finally:
        conn.close()
    
    return redirect(url_for('goal_detail', goal_id=goal_id))

@app.route('/forecast')
def cash_flow_forecast():
    """Cash flow forecast page."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get forecast months parameter
    months = int(request.args.get('months', 3))
    
    # Get all recurring transactions
    cursor.execute("""
    SELECT id, description, amount, type, frequency, day_of_month, day_of_week,
           start_date, end_date, category
    FROM recurring_forecasts
    ORDER BY type DESC, amount DESC  -- Income first
    """)
    
    recurring_items = [dict(item) for item in cursor.fetchall()]
    
    conn.close()
    
    # Generate forecast data
    today = datetime.date.today()
    end_date = today + datetime.timedelta(days=30 * months)
    
    forecast_data = {}
    
    for item in recurring_items:
        # Skip if end date is in the past
        if item['end_date'] and today > datetime.datetime.strptime(item['end_date'], '%Y-%m-%d').date():
            continue
        
        # Calculate occurrences within forecast period
        start = max(datetime.datetime.strptime(item['start_date'], '%Y-%m-%d').date(), today)
        current_date = start
        
        while current_date <= end_date:
            # Add to forecast
            month_key = current_date.strftime('%Y-%m')
            if month_key not in forecast_data:
                forecast_data[month_key] = {
                    'income': 0,
                    'expenses': 0,
                    'items': []
                }
            
            # Update totals
            if item['amount'] > 0:
                forecast_data[month_key]['income'] += item['amount']
            else:
                forecast_data[month_key]['expenses'] += abs(item['amount'])
            
            # Add item details
            forecast_data[month_key]['items'].append({
                'date': current_date.strftime('%Y-%m-%d'),
                'description': item['description'],
                'amount': item['amount'],
                'type': item['type'],
                'category': item['category']
            })
            
            # Calculate next occurrence based on frequency
            if item['frequency'] == 'daily':
                current_date += datetime.timedelta(days=1)
            elif item['frequency'] == 'weekly':
                current_date += datetime.timedelta(weeks=1)
            elif item['frequency'] == 'biweekly':
                current_date += datetime.timedelta(weeks=2)
            elif item['frequency'] == 'monthly':
                # Move to next month
                year = current_date.year + ((current_date.month) // 12)
                month = (current_date.month % 12) + 1
                # Ensure day_of_month is treated as an integer
                day_val = item['day_of_month'] if isinstance(item['day_of_month'], int) else current_date.day
                # Get the last day of the month to check against
                last_day = (datetime.date(year, month % 12 + 1, 1) if month < 12 else datetime.date(year + 1, 1, 1)) - datetime.timedelta(days=1)
                day = min(day_val, last_day.day)
                current_date = datetime.date(year, month, day)
            elif item['frequency'] == 'quarterly':
                # Move 3 months ahead
                month = current_date.month + 3
                year = current_date.year + ((month - 1) // 12)
                month = ((month - 1) % 12) + 1
                # Get the last day of the month to check against
                last_day = (datetime.date(year, month % 12 + 1, 1) if month < 12 else datetime.date(year + 1, 1, 1)) - datetime.timedelta(days=1)
                day = min(current_date.day, last_day.day)
                current_date = datetime.date(year, month, day)
            elif item['frequency'] == 'annual':
                # Move 1 year ahead
                current_date = datetime.date(current_date.year + 1, current_date.month, current_date.day)
    
    # Sort months
    sorted_months = sorted(forecast_data.keys())
    
    # Calculate running balance
    balance = 0
    monthly_data = []
    
    for month in sorted_months:
        data = forecast_data[month]
        net = data['income'] - data['expenses']
        balance += net
        
        monthly_data.append({
            'month': month,
            'income': data['income'],
            'expenses': data['expenses'],
            'net': net,
            'balance': balance,
            'items': sorted(data['items'], key=lambda x: x['date'])
        })
    
    # Create forecast chart
    if monthly_data:
        chart_months = [m['month'] for m in monthly_data]
        incomes = [m['income'] for m in monthly_data]
        expenses = [m['expenses'] for m in monthly_data]
        balances = [m['balance'] for m in monthly_data]
        
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        
        fig.add_trace(
            go.Bar(x=chart_months, y=incomes, name="Income", marker_color='lightseagreen'),
            secondary_y=False,
        )
        
        fig.add_trace(
            go.Bar(x=chart_months, y=expenses, name="Expenses", marker_color='indianred'),
            secondary_y=False,
        )
        
        fig.add_trace(
            go.Scatter(x=chart_months, y=balances, name="Balance", marker_color='royalblue'),
            secondary_y=True,
        )
        
        fig.update_layout(
            title='Cash Flow Forecast',
            barmode='group',
            template='plotly_white'
        )
        
        fig.update_yaxes(title_text="Monthly Amount ($)", secondary_y=False)
        fig.update_yaxes(title_text="Cumulative Balance ($)", secondary_y=True)
        
        forecast_chart = fig.to_json()
    else:
        forecast_chart = None
    
    return render_template(
        'forecast.html',
        monthly_data=monthly_data,
        forecast_chart=forecast_chart,
        months=months
    )

@app.route('/forecast/new', methods=['GET', 'POST'])
def new_recurring():
    """Add a new recurring transaction for forecasting."""
    if request.method == 'GET':
        # Get categories for suggestions
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
        SELECT DISTINCT category
        FROM consolidated_transactions
        WHERE category IS NOT NULL AND category != ''
        """)
        
        categories = [row['category'] for row in cursor.fetchall()]
        conn.close()
        
        return render_template('new_recurring.html', categories=categories)
    
    elif request.method == 'POST':
        # Process form data to create a new recurring transaction
        description = request.form.get('description')
        amount = float(request.form.get('amount'))
        tx_type = request.form.get('type')
        frequency = request.form.get('frequency')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date') or None
        category = request.form.get('category')
        notes = request.form.get('notes', '')
        
        # Process day_of_month and day_of_week based on frequency
        day_of_month = None
        day_of_week = None
        
        if frequency == 'monthly':
            day_of_month = int(request.form.get('day_of_month'))
        elif frequency in ['weekly', 'biweekly']:
            day_of_week = int(request.form.get('day_of_week'))
        
        # If expense, make amount negative
        if tx_type == 'expense':
            amount = -abs(amount)
        
        # Create the recurring transaction
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            current_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
            INSERT INTO recurring_forecasts 
            (description, amount, type, frequency, day_of_month, day_of_week,
             start_date, end_date, created_at, updated_at, category, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (description, amount, tx_type, frequency, day_of_month, day_of_week,
                 start_date, end_date, current_timestamp, current_timestamp, category, notes))
            
            conn.commit()
            flash("Recurring transaction added successfully", "success")
        except sqlite3.Error as e:
            conn.rollback()
            flash(f"Error adding recurring transaction: {e}", "error")
        finally:
            conn.close()
        
        return redirect(url_for('cash_flow_forecast'))

@app.route('/categorize')
def categorize():
    """Smart categorization page."""
    # Get uncategorized transactions
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT id, description, amount, source, date_posted 
    FROM consolidated_transactions
    WHERE (category IS NULL OR category = '')
    ORDER BY date_posted DESC
    LIMIT 100
    """)
    
    transactions = [dict(tx) for tx in cursor.fetchall()]
    
    # Get valid categories for suggestions
    cursor.execute("""
    SELECT DISTINCT category 
    FROM consolidated_transactions 
    WHERE category IS NOT NULL AND category != ''
    """)
    
    categories = [row['category'] for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template(
        'categorize.html',
        transactions=transactions,
        categories=categories
    )

@app.route('/categorize/bulk', methods=['POST'])
def categorize_bulk():
    """Process bulk categorization."""
    transaction_ids = request.form.getlist('transaction_id')
    categories = request.form.getlist('category')
    
    if len(transaction_ids) != len(categories):
        flash("Invalid form data", "error")
        return redirect(url_for('categorize'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    success_count = 0
    
    for tx_id, category in zip(transaction_ids, categories):
        if not category:
            continue
            
        try:
            cursor.execute("""
            UPDATE consolidated_transactions
            SET category = ?
            WHERE id = ?
            """, (category, tx_id))
            success_count += 1
        except sqlite3.Error as e:
            print(f"Error updating transaction {tx_id}: {e}")
    
    conn.commit()
    conn.close()
    
    flash(f"Successfully categorized {success_count} transactions", "success")
    return redirect(url_for('categorize'))

@app.route('/categorize/train', methods=['POST'])
def train_model():
    """Train categorization model."""
    # This will call the train_category_classifier function
    result = train_category_classifier(DB_PATH, MODEL_DIR)
    
    if result:
        flash("Category model trained successfully", "success")
    else:
        flash("Failed to train category model", "error")
    
    return redirect(url_for('categorize'))

@app.route('/categorize/auto', methods=['POST'])
def auto_categorize():
    """Run auto-categorization with AI."""
    limit = int(request.form.get('limit', 100))
    
    # Redirect to results page where JavaScript will poll for results
    return render_template('categorize_processing.html', limit=limit)

@app.route('/categorize/auto/process')
def process_auto_categorize():
    """Background process for auto-categorization."""
    limit = int(request.args.get('limit', 100))
    
    # Mock the categorize_transactions function to return JSON
    # In a real app, you'd use a background task queue
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get uncategorized transactions
    cursor.execute("""
    SELECT id, description, amount, source, date_posted 
    FROM consolidated_transactions
    WHERE (category IS NULL OR category = '')
    ORDER BY date_posted DESC
    LIMIT ?
    """, (limit,))
    
    transactions = [dict(tx) for tx in cursor.fetchall()]
    conn.close()
    
    # Usually would call categorize_transactions but we'll simulate it
    results = {
        'total': len(transactions),
        'processed': 0,
        'suggestions': []
    }
    
    for tx in transactions:
        # Call suggest_category_for_transaction but handle if not imported
        # For now just add dummy suggestions
        results['suggestions'].append({
            'id': tx['id'],
            'description': tx['description'],
            'amount': tx['amount'],
            'suggested_category': 'Category Suggestion',
            'confidence': 0.85
        })
        results['processed'] += 1
    
    return jsonify(results)

@app.route('/analyze')
def analyze():
    """Spending analysis page."""
    # Get the analysis data
    conn = get_db_connection()
    
    # Date range of transactions
    cursor = conn.cursor()
    cursor.execute("""
    SELECT MIN(date_posted), MAX(date_posted)
    FROM consolidated_transactions
    """)
    
    min_date, max_date = cursor.fetchone()
    
    # Get spending by category for the last 3 months
    date_str = str(max_date).split(' ')[0]  # gives "YYYY-MM-DD"
    three_months_ago = (datetime.datetime.strptime(date_str, '%Y-%m-%d') - datetime.timedelta(days=90)).strftime('%Y-%m-%d')
    
    cursor.execute("""
    SELECT category, SUM(amount) as total_spent
    FROM consolidated_transactions
    WHERE category IS NOT NULL 
    AND category != ''
    AND date_posted >= ?
    AND amount < 0  -- Only expenses (negative amounts)
    GROUP BY category
    ORDER BY total_spent ASC  -- Ascending because expenses are negative
    LIMIT 10
    """, (three_months_ago,))

    rows = cursor.fetchall()
    top_categories = [dict(r) for r in rows]
    
    # Create chart for top spending categories
    categories = [row['category'] for row in top_categories]
    amounts = [abs(row['total_spent']) for row in top_categories]
    
    fig1 = go.Figure(data=[go.Bar(
        x=amounts,
        y=categories,
        orientation='h',
        marker_color='indianred'
    )])
    
    fig1.update_layout(
        title='Top Spending Categories',
        xaxis_title='Amount ($)',
        yaxis_title='Category',
        template='plotly_white'
    )
    
    category_chart = fig1.to_json()
    
    # Monthly spending trend
    cursor.execute("""
    SELECT 
        strftime('%Y-%m', date_posted) as month,
        SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as expenses,
        SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income
    FROM consolidated_transactions
    GROUP BY strftime('%Y-%m', date_posted)
    ORDER BY month ASC
    """)
    
    monthly_data = [dict(row) for row in cursor.fetchall()]
    
    # Create chart for monthly trend
    months = [row['month'] for row in monthly_data]
    expenses = [abs(row['expenses']) for row in monthly_data]
    incomes = [row['income'] for row in monthly_data]
    
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=months,
        y=expenses,
        mode='lines+markers',
        name='Expenses',
        line=dict(color='indianred', width=3)
    ))
    
    fig2.add_trace(go.Scatter(
        x=months,
        y=incomes,
        mode='lines+markers',
        name='Income',
        line=dict(color='lightseagreen', width=3)
    ))
    
    fig2.update_layout(
        title='Monthly Income and Expenses',
        xaxis_title='Month',
        yaxis_title='Amount ($)',
        template='plotly_white'
    )
    
    monthly_chart = fig2.to_json()
    
    # Get recurring expenses
    cursor.execute("""
    SELECT description, category, AVG(amount) as avg_amount, COUNT(*) as occurrence_count
    FROM consolidated_transactions
    WHERE amount < 0
    AND date_posted >= ?
    GROUP BY description, category
    HAVING COUNT(*) >= 3
    ORDER BY avg_amount ASC
    LIMIT 10
    """, (three_months_ago,))
    
    recurring_expenses = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template(
        'analyze.html',
        date_range=f"{min_date} to {max_date}",
        top_categories=top_categories,
        monthly_data=monthly_data,
        recurring_expenses=recurring_expenses,
        category_chart=category_chart,
        monthly_chart=monthly_chart
    )

# ---------------------------
# Tax Depreciation Routes
# ---------------------------

@app.route('/tax')
def tax_depreciation():
    """Section 179 & Depreciation page."""
    current_year = datetime.datetime.now().year
    
    # Get Section 179 limit for current year
    section_179_limit = get_section_179_limit(current_year)
    
    # Get tax items
    tax_items = get_tax_items()
    
    # Separate Section 179 and regular depreciation items
    section_179_items = [item for item in tax_items if item['use_section_179']]
    depreciation_items = [item for item in tax_items if not item['use_section_179']]
    
    # Calculate totals
    section_179_total = sum(item['business_amount'] for item in section_179_items)
    depreciation_total = sum(
        calculate_depreciation(
            item['business_amount'],
            item['depreciation_years'],
            int(item['purchase_date'].split('-')[0]),
            current_year
        ) for item in depreciation_items
    )
    
    # Get equipment transactions for dropdown
    equipment_transactions = get_equipment_transactions()
    
    # For depreciation schedule, prepare data for each item
    items_with_schedule = []
    for item in depreciation_items:
        purchase_year = int(item['purchase_date'].split('-')[0])
        # Only calculate schedule for non-Section 179 items
        if not item['use_section_179']:
            # Get depreciation schedule
            schedule = generate_depreciation_schedule(item['id'])
            
            # Calculate current year's depreciation
            current_year_depreciation = next(
                (s['depreciation'] for s in schedule if s['year'] == current_year),
                0
            )
            
            # Calculate remaining value
            remaining_value = next(
                (s['remaining'] for s in schedule if s['year'] == current_year),
                0
            )
            
            # Add to items with schedule
            items_with_schedule.append({
                'description': item['description'],
                'purchase_date': item['purchase_date'],
                'amount': item['business_amount'],
                'yearly_depreciation': [s['depreciation'] for s in schedule],
                'remaining_value': remaining_value
            })
    
    # Create depreciation chart
    depreciation_years = list(range(current_year, current_year + 5))
    
    if items_with_schedule:
        yearly_totals = {year: 0 for year in depreciation_years}
        
        # Calculate yearly totals
        for year in depreciation_years:
            for item in tax_items:
                if item['use_section_179'] and int(item['purchase_date'].split('-')[0]) == year:
                    # Section 179 deduction in purchase year
                    yearly_totals[year] += item['business_amount']
                else:
                    # Regular depreciation
                    yearly_totals[year] += calculate_depreciation(
                        item['business_amount'],
                        item['depreciation_years'],
                        int(item['purchase_date'].split('-')[0]),
                        year
                    )
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=list(yearly_totals.keys()),
            y=list(yearly_totals.values()),
            name='Tax Deduction',
            marker_color='royalblue'
        ))
        
        fig.update_layout(
            title='Projected Tax Deductions by Year',
            xaxis_title='Tax Year',
            yaxis_title='Deduction Amount ($)',
            template='plotly_white'
        )
        
        depreciation_chart = fig.to_json()
    else:
        depreciation_chart = None
    
    return render_template(
        'tax_depreciation.html',
        section_179_items=section_179_items,
        depreciation_items=items_with_schedule,
        equipment_transactions=equipment_transactions,
        section_179_total=section_179_total,
        depreciation_total=depreciation_total,
        section_179_limit=section_179_limit,
        current_year=current_year,
        depreciation_years=depreciation_years,
        depreciation_chart=depreciation_chart
    )

@app.route('/tax/transaction/<int:transaction_id>')
def get_transaction_for_tax(transaction_id):
    """API endpoint to get transaction data for tax item form."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT id, date_posted, description, amount, category
    FROM consolidated_transactions
    WHERE id = ?
    """, (transaction_id,))
    
    transaction = cursor.fetchone()
    conn.close()
    
    if not transaction:
        return jsonify({"error": "Transaction not found"}), 404
    
    return jsonify(dict(transaction))

@app.route('/tax/item/add', methods=['POST'])
def add_tax_item_route():
    """Add a new tax item."""
    description = request.form.get('description')
    purchase_date = request.form.get('purchase_date')
    amount = float(request.form.get('amount', 0))
    business_use_percentage = int(request.form.get('business_use_percentage', 100))
    depreciation_years = int(request.form.get('depreciation_years', 5))
    use_section_179 = 'use_section_179' in request.form
    transaction_id = request.form.get('transaction_id')
    notes = request.form.get('notes', '')
    
    # Convert empty transaction_id to None
    if not transaction_id:
        transaction_id = None
    else:
        transaction_id = int(transaction_id)
    
    # Add tax item
    item_id = add_tax_item(
        description, purchase_date, amount, business_use_percentage,
        depreciation_years, use_section_179, transaction_id, notes
    )
    
    if item_id:
        flash("Tax item added successfully", "success")
    else:
        flash("Error adding tax item", "error")
    
    return redirect(url_for('tax_depreciation'))

@app.route('/tax/item/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_tax_item(item_id):
    """Edit a tax item."""
    if request.method == 'GET':
        # Get tax item
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM tax_items WHERE id = ?", (item_id,))
        item = cursor.fetchone()
        
        if not item:
            flash("Tax item not found", "error")
            return redirect(url_for('tax_depreciation'))
        
        conn.close()
        
        return render_template('tax_item_edit.html', item=dict(item))
    
    elif request.method == 'POST':
        # Update tax item
        description = request.form.get('description')
        purchase_date = request.form.get('purchase_date')
        amount = float(request.form.get('amount', 0))
        business_use_percentage = int(request.form.get('business_use_percentage', 100))
        depreciation_years = int(request.form.get('depreciation_years', 5))
        use_section_179 = 'use_section_179' in request.form
        notes = request.form.get('notes', '')
        
        success = update_tax_item(
            item_id, description, purchase_date, amount, business_use_percentage,
            depreciation_years, use_section_179, notes
        )
        
        if success:
            flash("Tax item updated successfully", "success")
        else:
            flash("Error updating tax item", "error")
        
        return redirect(url_for('tax_depreciation'))

@app.route('/tax/item/<int:item_id>/delete', methods=['POST'])
def delete_tax_item_route(item_id):
    """Delete a tax item."""
    success = delete_tax_item(item_id)
    
    if success:
        flash("Tax item deleted successfully", "success")
    else:
        flash("Error deleting tax item", "error")
    
    return redirect(url_for('tax_depreciation'))

@app.route('/tax/report')
def tax_report():
    """Generate a tax report for the specified year."""
    tax_year = int(request.args.get('year', datetime.datetime.now().year))
    
    # Generate tax report
    report = generate_tax_report(tax_year)
    
    return render_template('tax_report.html', **report)

@app.route('/tax/report/download')
def download_tax_report():
    """Download tax report as CSV."""
    tax_year = int(request.args.get('year', datetime.datetime.now().year))
    
    # Generate tax report
    report = generate_tax_report(tax_year)
    
    # Create CSV data
    output = []
    
    # Header
    output.append(f"Tax Deduction Report for {tax_year}")
    output.append("")
    
    # Summary
    output.append("Summary:")
    output.append(f"Section 179 Total,${report['section_179_total']:.2f}")
    output.append(f"Section 179 Limit,${report['section_179_limit']:.2f}")
    output.append(f"Section 179 Deduction,${report['section_179_deduction']:.2f}")
    output.append(f"Regular Depreciation,${report['depreciation_total']:.2f}")
    output.append(f"Total Deduction,${report['total_deduction']:.2f}")
    output.append("")
    
    # Section 179 items
    if report['section_179_items']:
        output.append("Section 179 Property:")
        output.append("Description,Date Placed in Service,Cost Basis,Business Use %,Business Cost,Section 179 Deduction")
        for item in report['section_179_items']:
            output.append(f"{item['description']},{item['purchase_date']},${item['amount']:.2f},{item['business_use_percentage']}%,${item['business_amount']:.2f},${item['section_179_amount']:.2f}")
    
    output.append("")
    
    # Depreciation items
    if report['depreciation_items']:
        output.append("Regular Depreciation:")
        output.append("Description,Date Placed in Service,Cost Basis,Recovery Period,Prior Depreciation,Current Year Depreciation,Remaining Basis")
        for item in report['depreciation_items']:
            output.append(f"{item['description']},{item['purchase_date']},${item['amount']:.2f},{item['depreciation_years']} years,${item['prior_depreciation']:.2f},${item['current_year_depreciation']:.2f},${item['remaining_value']:.2f}")
    
    # Create response
    csv_data = "\n".join(output)
    response = Response(csv_data, mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename=tax_report_{tax_year}.csv'
    
    return response

@app.route('/tax/report/generate')
def generate_tax_report_route():
    """Route to generate a tax report."""
    return redirect(url_for('tax_report'))

@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files."""
    return send_from_directory(os.path.join(os.path.dirname(__file__), 'static'), filename)

if __name__ == '__main__':
    app.run(debug=True)
