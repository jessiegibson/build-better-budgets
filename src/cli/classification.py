import os
import sys
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any, Union

from ml_classifier import (
    TransactionClassifier, batch_classification,
    detect_recurring_transactions, get_similar_transactions
)

from tax_management import (
    TaxItem, create_tax_depreciation_report, calculate_tax_deductions
)

def show_budget_info() -> None:
    """Display information about all budgets."""
    budgets = get_all_budgets()

    if not budgets:
        print("No budgets found.")
        return

    print("\n=== Budgets ===")
    print(f"{'ID':<5} {'Name':<30} {'Period':<25} {'Amount':<15} {'Status'}")
    print("-" * 80)

    for budget in budgets:
        status = budget['status']
        status_display = {
            'current': '🟢 Current',
            'past': '🔴 Past',
            'future': '🔵 Future'
        }.get(status, status)

        print(f"{budget['id']:<5} {budget['name'][:30]:<30} "
              f"{budget['start_date']} - {budget['end_date']:<10} "
              f"${budget['total_amount']:<15.2f} {status_display}")

def show_goal_info() -> None:
    """Display information about all goals."""
    goals = get_all_goals()

    if not goals:
        print("No goals found.")
        return

    print("\n=== Financial Goals ===")
    print(f"{'ID':<5} {'Name':<25} {'Target':<15} {'Current':<15} {'Completion':<15} {'Target Date'}")
    print("-" * 90)

    for goal in goals:
        progress = goal['percent_complete']
        progress_bar = "▓" * int(progress / 5) + "░" * (20 - int(progress / 5))

        print(f"{goal['id']:<5} {goal['name'][:25]:<25} "
              f"${goal['target_amount']:<15.2f} ${goal['current_amount']:<15.2f} "
              f"{progress_bar} {progress:5.1f}% {goal['target_date']}")

def display_forecast(months: int) -> None:
    """
    Display forecasted expenses.

    Args:
        months: Number of months to forecast
    """
    forecast = forecast_expenses(months)

    print(f"\n=== Expense Forecast for Next {months} Months ===")

    for month_key, expenses in forecast.items():
        month_date = datetime.strptime(month_key, '%Y-%m')
        month_name = month_date.strftime('%B %Y')
        total = sum(abs(e['amount']) for e in expenses)

        print(f"\n{month_name}: ${total:.2f} ({len(expenses)} expenses)")

        if expenses:
            print(f"{'Date':<12} {'Amount':<10} {'Category':<15} {'Description'}")
            print("-" * 70)

            for expense in expenses:
                category = expense.get('category') or 'Uncategorized'
                print(f"{expense['date']:<12} ${abs(expense['amount']):<10.2f} "
                      f"{category[:15]:<15} {expense['description'][:40]}")


# ---------------------------
# Transaction Classification
# ---------------------------

def sample_transactions(db_path: str, fraction: float = 0.10) -> List[Tuple]:
    """
    Take a sample from the transactions for testing or model training.

    Args:
        db_path: Path to the SQLite database
        fraction: Fraction of transactions to sample (0-1)

    Returns:
        List of transaction tuples
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Count the total transactions in the consolidated table
    cursor.execute("SELECT COUNT(*) FROM consolidated_transactions")
    total = cursor.fetchone()[0]

    # Calculate sample size (ensuring at least one row is returned)
    sample_size = max(1, int(total * fraction))
    print(f"Total transactions: {total}, sampling: {sample_size}")

    # Randomly select sample_size transactions
    cursor.execute(
        "SELECT * FROM consolidated_transactions ORDER BY RANDOM() LIMIT ?",
        (sample_size,)
    )
    sample = cursor.fetchall()
    conn.close()
    return sample


def detect_recurring_transactions(db_path: str) -> int:
    """
    Detect recurring transactions by finding similar descriptions and amounts on a monthly basis.

    Args:
        db_path: Path to the SQLite database

    Returns:
        Number of recurring transactions identified
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Use row factory for named columns
    cursor = conn.cursor()

    print("Detecting recurring transactions...")

    # First, extract unique transaction descriptions
    cursor.execute("""
        SELECT DISTINCT description
        FROM consolidated_transactions
        WHERE description IS NOT NULL AND description != ''
    """)

    all_descriptions = [row['description'] for row in cursor.fetchall()]

    # Count of recurring transactions identified
    recurring_count = 0

    # Process each description
    for desc in all_descriptions:
        # Get transactions with this description
        cursor.execute("""
            SELECT id, date_posted, description, amount, source
            FROM consolidated_transactions
            WHERE description = ?
            ORDER BY date_posted
        """, (desc,))

        transactions = cursor.fetchall()

        # Skip if only one transaction with this description
        if len(transactions) < 2:
            continue

        # Convert date_posted to datetime objects and group by month
        months = {}
        for txn in transactions:
            try:
                date = pd.to_datetime(txn['date_posted'])
                month_key = f"{date.year}-{date.month:02d}"

                if month_key not in months:
                    months[month_key] = []

                months[month_key].append(txn)
            except:
                continue

        # Check if there are similar transactions in multiple months
        if len(months) >= 2:
            # Calculate average amount
            amounts = [txn['amount'] for txn in transactions]
            avg_amount = sum(amounts) / len(amounts)

            # Calculate standard deviation
            std_amount = (sum((a - avg_amount) ** 2 for a in amounts) / len(amounts)) ** 0.5

            # If standard deviation is small relative to average (consistent amounts)
            # or there are >= 3 months with the same description, mark as recurring
            is_recurring = (std_amount / abs(avg_amount) < 0.1 if avg_amount != 0 else False) or len(months) >= 3

            if is_recurring:
                # Generate a recurring group ID based on the first few chars of description
                group_id = re.sub(r'\W+', '', desc)[:20].upper()

                # Mark all these transactions as recurring
                for txn in transactions:
                    cursor.execute("""
                        UPDATE consolidated_transactions
                        SET recurring = 1,
                            recurring_group = ?,
                            recurring_freq = 'MONTHLY'
                        WHERE id = ?
                    """, (group_id, txn['id']))
                    recurring_count += 1

    conn.commit()
    print(f"Identified {recurring_count} recurring transactions in {len(all_descriptions)} unique descriptions")
    conn.close()

    return recurring_count


def interactive_classification(db_path: str, sample_size: int = 5, mode: str = 'all') -> None:
    """
    Pull a sample of unlabeled transactions and let the user classify them.

    Args:
        db_path: Path to the SQLite database
        sample_size: Number of transactions to classify in one batch
        mode: Classification mode - 'all', 'rental', 'recurring', 'subscription', 'equipment', etc.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Build the WHERE clause based on the mode
    where_clause = ""
    if mode == 'rental':
        where_clause = "WHERE rental_related IS NULL"
    elif mode == 'recurring':
        where_clause = "WHERE recurring IS NULL"
    elif mode == 'subscription':
        where_clause = "WHERE subscription IS NULL"
    elif mode == 'tax':
        where_clause = "WHERE tax_deductible IS NULL"
    elif mode == 'equipment':
        where_clause = "WHERE equipment_tools IS NULL"
    else:  # 'all' or default
        where_clause = "WHERE rental_related IS NULL OR recurring IS NULL OR subscription IS NULL OR equipment_tools IS NULL"

    # Get a sample of transactions that have not been fully classified
    query = f"""
        SELECT id, date_posted, description, amount, source
        FROM consolidated_transactions
        {where_clause}
        ORDER BY date_posted DESC
        LIMIT ?
    """

    cursor.execute(query, (sample_size,))
    transactions = cursor.fetchall()

    if not transactions:
        print(f"No transactions found for {mode} classification.")
        conn.close()
        return

    for txn in transactions:
        txn_id, date, description, amount, source = txn
        print(f"\nTransaction ID: {txn_id}")
        print(f"Date: {date}")
        print(f"Source: {source}")
        print(f"Description: {description}")
        print(f"Amount: {amount}")

        updates = {}

        # Only ask relevant questions based on mode
        if mode in ['all', 'rental']:
            rental_input = input("Is this a rental property expense? (y/n/s=skip): ").strip().lower()
            if rental_input != 's':
                updates['rental_related'] = 1 if rental_input == 'y' else 0

                if rental_input == 'y':
                    mu_input = input("Is it an upgrade or maintenance? (u=upgrade/m=maintenance/s=skip): ").strip().lower()
                    if mu_input != 's':
                        if mu_input == "u":
                            updates['maintenance_upgrade'] = "Upgrade"
                        elif mu_input == "m":
                            updates['maintenance_upgrade'] = "Maintenance"

        if mode in ['all', 'recurring']:
            recurring_input = input("Is this a recurring transaction? (y/n/s=skip): ").strip().lower()
            if recurring_input != 's':
                updates['recurring'] = 1 if recurring_input == 'y' else 0

                if recurring_input == 'y':
                    freq_input = input("Frequency (m=monthly/w=weekly/q=quarterly/y=yearly/s=skip): ").strip().lower()
                    if freq_input != 's':
                        freq_map = {'m': 'MONTHLY', 'w': 'WEEKLY', 'q': 'QUARTERLY', 'y': 'YEARLY'}
                        updates['recurring_freq'] = freq_map.get(freq_input, 'UNKNOWN')

                    group_input = input("Recurring group name (or enter for auto-generate): ").strip()
                    if group_input:
                        updates['recurring_group'] = group_input
                    else:
                        # Auto-generate a group name from the description
                        group_id = re.sub(r'\W+', '', description)[:20].upper()
                        updates['recurring_group'] = group_id

        if mode in ['all', 'subscription']:
            sub_input = input("Is this a subscription service? (y/n/s=skip): ").strip().lower()
            if sub_input != 's':
                updates['subscription'] = 1 if sub_input == 'y' else 0

        if mode in ['all', 'tax']:
            tax_input = input("Is this tax deductible? (y/n/s=skip): ").strip().lower()
            if tax_input != 's':
                updates['tax_deductible'] = 1 if tax_input == 'y' else 0

        if mode in ['all', 'equipment']:
            equip_input = input("Is this depreciable equipment or a tool? (y/n/s=skip): ").strip().lower()
            if equip_input != 's':
                updates['equipment_tools'] = 1 if equip_input == 'y' else 0

                if equip_input == 'y':
                    # Capture purchase date (use transaction date as default)
                    purchase_date = input(f"Purchase date [{date}] (YYYY-MM-DD or s=skip): ").strip()
                    if purchase_date != 's':
                        updates['purchase_date'] = purchase_date if purchase_date else date

                    # Capture asset value (use amount as default)
                    asset_value = input(f"Asset value [{amount}] (or s=skip): ").strip()
                    if asset_value != 's':
                        try:
                            updates['asset_value'] = float(asset_value) if asset_value else amount
                        except ValueError:
                            print("Invalid value, using transaction amount")
                            updates['asset_value'] = amount

                    # Capture depreciation years
                    dep_years = input("Depreciation period in years (or s=skip): ").strip()
                    if dep_years != 's':
                        try:
                            updates['depreciation_years'] = int(dep_years) if dep_years else None
                        except ValueError:
                            print("Invalid value, skipping")

        if mode in ['all']:
            category_input = input("Enter expense category (or s=skip): ").strip()
            if category_input != 's':
                updates['expense_category'] = category_input

            notes_input = input("Additional notes (or s=skip): ").strip()
            if notes_input != 's':
                updates['notes'] = notes_input

        # Only update if we have something to update
        if updates:
            # Build the SET clause dynamically
            set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
            values = list(updates.values()) + [txn_id]  # Add txn_id at the end for the WHERE clause

            # Execute the UPDATE
            cursor.execute(f"""
                UPDATE consolidated_transactions
                SET {set_clause}
                WHERE id = ?
            """, values)
            conn.commit()
            print(f"Transaction {txn_id} updated with {', '.join(updates.keys())}.")
        else:
            print(f"Transaction {txn_id} skipped.")

    # Show how many transactions are left to classify
    remaining_counts = {}
    for field in ['rental_related', 'recurring', 'subscription', 'tax_deductible', 'equipment_tools']:
        cursor.execute(f"SELECT COUNT(*) FROM consolidated_transactions WHERE {field} IS NULL")
        remaining_counts[field] = cursor.fetchone()[0]

    print("\nRemaining transactions to classify:")
    print(f"Rental: {remaining_counts['rental_related']}")
    print(f"Recurring: {remaining_counts['recurring']}")
    print(f"Subscription: {remaining_counts['subscription']}")
    print(f"Tax Deductible: {remaining_counts['tax_deductible']}")
    print(f"Equipment/Tools: {remaining_counts['equipment_tools']}")

    conn.close()


# ---------------------------
# Smart Categorization with AI
# ---------------------------

def train_category_classifier(db_path: str, model_dir: str) -> Optional[Pipeline]:
    """
    Train a machine learning model to automatically categorize transactions.

    Args:
        db_path: Path to the SQLite database
        model_dir: Directory to save the trained model

    Returns:
        Trained classification model
    """
    # Create model dir if it doesn't exist
    os.makedirs(model_dir, exist_ok=True)

    # Make sure database directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if consolidated_transactions table exists
    cursor.execute("""
    SELECT count(name) FROM sqlite_master
    WHERE type='table' AND name='consolidated_transactions'
    """)

    if cursor.fetchone()[0] == 0:
        print("Error: The consolidated_transactions table doesn't exist yet.")
        print("Please run with --consolidate flag first to create and populate the table.")
        print("Example: python src/app.py --consolidate")
        conn.close()
        return None

    # Get all categorized transactions for training
    query = """
    SELECT description, amount, source, category
    FROM consolidated_transactions
    WHERE category IS NOT NULL AND category != ''
    """

    try:
        df = pd.read_sql_query(query, conn)
        conn.close()
    except (sqlite3.OperationalError, pd.errors.DatabaseError) as e:
        print(f"Database error: {e}")
        print("Please make sure you've imported transactions and consolidated them first.")
        print("Run: python src/app.py --consolidate")
        conn.close()
        return None

    if df.empty or len(df) < 20:  # Need a reasonable amount of data
        print("Not enough categorized transactions to train a model.")
        print("Please categorize more transactions and try again.")
        return None

    # Count categories to see if we have enough data
    category_counts = df['category'].value_counts()
    valid_categories = category_counts[category_counts >= 5].index.tolist()

    if len(valid_categories) < 3:  # Need at least a few categories
        print(f"Need more diverse categories. Only found {len(valid_categories)} with 5+ examples.")
        print("Please add more varied transactions and try again.")
        return None

    # Filter to only include categories with enough examples
    df = df[df['category'].isin(valid_categories)]

    print(f"Training with {len(df)} transactions across {len(valid_categories)} categories.")
    print(f"Top categories: {', '.join(category_counts.index[:5])}")

    # Convert amount to numeric and handle any non-numeric values
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    df['amount'] = df['amount'].fillna(0)

    # Ensure description is a string and handle null values
    df['description'] = df['description'].fillna('').astype(str)

    # Prepare features: combine description with other features
    df['amount_str'] = df['amount'].apply(lambda x: 'high' if abs(x) > 100 else 'medium' if abs(x) > 20 else 'low')
    df['text_features'] = df['description'] + ' ' + df['amount_str']

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        df['text_features'],
        df['category'],
        test_size=0.25,
        random_state=42
    )

    # Create a pipeline with TF-IDF and RandomForest
    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(
            min_df=2,
            max_df=dir: Directory where models are stored
        limit: Maximum number of transactions to process
    """
    # Load the model
    #
    """
    model = get_latest_category_model(model_dir)
    if model is None:
        print("No category classification model found.")
        print("Please train a model first with --train-category-model")
        return

    # Get valid categories
    valid_categories = get_valid_categories(model_dir)
    if not valid_categories:
        print("No valid categories found for the model.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if consolidated_transactions table exists
    cursor.execute("""
    SELECT count(name) FROM sqlite_master
    WHERE type='table' AND name='consolidated_transactions'
    """)

    if cursor.fetchone()[0] == 0:
        print("Error: The consolidated_transactions table doesn't exist yet.")
        print("Please run with --consolidate flag first to create and populate the table.")
        print("Example: python src/app.py --consolidate")
        conn.close()
        return

    # Get uncategorized transactions
    try:
        query = f"""
        SELECT id, description, amount, source, date_posted
        FROM consolidated_transactions
        WHERE (category IS NULL OR category = '')
        ORDER BY date_posted DESC
        LIMIT {limit}
        """

        df = pd.read_sql_query(query, conn)
    except (sqlite3.OperationalError, pd.errors.DatabaseError) as e:
        print(f"Database error: {e}")
        print("Please make sure you've imported transactions and consolidated them first.")
        print("Run: python src/app.py --consolidate")
        conn.close()
        return

    if df.empty:
        print("No uncategorized transactions found.")
        conn.close()
        return

    print(f"Found {len(df)} uncategorized transactions to process.")

    # Convert amount to numeric and handle any non-numeric values
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    df['amount'] = df['amount'].fillna(0)

    # Ensure description is a string and handle null values
    df['description'] = df['description'].fillna('').astype(str)

    # Prepare features for prediction
    df['amount_str'] = df['amount'].apply(lambda x: 'high' if abs(x) > 100 else 'medium' if abs(x) > 20 else 'low')
    df['text_features'] = df['description'] + ' ' + df['amount_str']

    # Make predictions
    print("Suggesting categories...")

    predictions = model.predict(df['text_features'])
    probabilities = model.predict_proba(df['text_features'])
    df['predicted_category'] = predictions
    df['confidence'] = [max(prob) for prob in probabilities]

    # Show predictions
    print("\nCategory Suggestions:")
    print(f"{'ID':<5} {'Description':<40} {'Amount':<10} {'Suggested Category':<20} {'Confidence':<10}")
    print("-" * 90)

    # Sort by confidence
    df_sorted = df.sort_values('confidence', ascending=False)

    # Show top suggestions
    for i, row in df_sorted.head(10).iterrows():
        desc = (row['description'][:37] + "...") if len(row['description']) > 40 else row['description']
        print(f"{row['id']:<5} {desc:<40} ${row['amount']:<8.2f} {row['predicted_category']:<20} {row['confidence']:.2f}")

    # Ask if we should apply predictions
    apply_mode = input("\nApply predictions? (a=all, h=high confidence only, i=interactive, n=none): ").strip().lower()

    if apply_mode in ['a', 'h', 'i']:
        cursor = conn.cursor()
        count = 0

        # Set confidence threshold
        confidence_threshold = 0.7 if apply_mode == 'h' else 0.0

        # Process each prediction
        for i, row in df_sorted.iterrows():
            # Skip low confidence predictions for 'high confidence' mode
            if apply_mode == 'h' and row['confidence'] < confidence_threshold:
                continue

            # For interactive mode, ask for each prediction
            if apply_mode == 'i':
                print(f"\nTransaction: {row['description']}")
                print(f"Amount: ${row['amount']:.2f}, Date: {row['date_posted']}")
                print(f"Suggested category: {row['predicted_category']} (confidence: {row['confidence']:.2f})")

                # Show prediction alternatives (top 3)
                category_probs = [(model.classes_[j], prob) for j, prob in enumerate(probabilities[i])]
                category_probs.sort(key=lambda x: x[1], reverse=True)

                print("Alternative categories:")
                for j, (cat, prob) in enumerate(category_probs[:3]):
                    print(f"{j+1}. {cat} ({prob:.2f})")

                choice = input("Accept suggestion? (y/n/1-3 for alternative/s to skip): ").strip().lower()

                if choice == 'y':
                    category = row['predicted_category']
                elif choice.isdigit() and 1 <= int(choice) <= 3:
                    category = category_probs[int(choice)-1][0]
                elif choice == 'n':
                    # Let user enter a custom category
                    print("Available categories:")
                    for j, cat in enumerate(valid_categories[:10]):
                        print(f"{j+1}. {cat}")
                    print("c. Custom category")

                    cat_choice = input("Enter category choice (1-10 or c): ").strip().lower()
                    if cat_choice == 'c':
                        category = input("Enter custom category: ").strip()
                    elif cat_choice.isdigit() and 1 <= int(cat_choice) <= len(valid_categories[:10]):
                        category = valid_categories[int(cat_choice)-1]
                    else:
                        print("Invalid choice, skipping.")
                        continue
                else:
                    # Skip this transaction
                    continue
            else:
                # For automatic modes (all or high confidence)
                category = row['predicted_category']

            # Update the category
            cursor.execute("""
            UPDATE consolidated_transactions
            SET category = ?
            WHERE id = ?
            """, (category, row['id']))

            count += 1

        conn.commit()
        print(f"\nApplied categories to {count} transactions.")
    else:
        print("No categories applied.")

    conn.close()


def suggest_category_for_transaction(description: str, amount: float, model_dir: str) -> Optional[str]:
"""
    Suggest a category for a given transaction based on its description and amount.

    Args:
        description: Transaction description text
        amount: Transaction amount
        model_dir: Directory where models are stored

    Returns:
        Suggested category or None if no model available
    """
    # Load the model
    model = get_latest_category_model(model_dir)
    if model is None:
        return None

    # Ensure amount is numeric
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        amount = 0

    # Ensure description is a string
    if description is None:
        description = ''
    else:
        description = str(description)

    # Prepare the features
    amount_str = 'high' if abs(amount) > 100 else 'medium' if abs(amount) > 20 else 'low'
    text_features = description + ' ' + amount_str

    # Make prediction
    prediction = model.predict([text_features])[0]
    probabilities = model.predict_proba([text_features])[0]
    confidence = max(probabilities)

    # Get top alternatives
    category_probs = [(model.classes_[i], prob) for i, prob in enumerate(probabilities)]
    category_probs.sort(key=lambda x: x[1], reverse=True)

    # Return the suggested category along with confidence and alternatives
    return {
        'category': prediction,
        'confidence': confidence,
        'alternatives': category_probs[:3]
    }
    def analyze_spending_patterns(db_path: str) -> None:
        """
        Analyze spending patterns to provide insights and recommendations.

        Args:
            db_path: Path to the SQLite database
        """
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print("\n=== Spending Pattern Analysis ===")

        # Check if consolidated_transactions table exists
        cursor.execute("""
        SELECT count(name) FROM sqlite_master
        WHERE type='table' AND name='consolidated_transactions'
        """)

        if cursor.fetchone()[0] == 0:
            print("Error: The consolidated_transactions table doesn't exist yet.")
            print("Please run with --consolidate flag first to create and populate the table.")
            print("Example: python src/app.py --consolidate")
            conn.close()
            return

        # Get the date range of transactions
        try:
            cursor.execute("""
            SELECT MIN(date_posted), MAX(date_posted)
            FROM consolidated_transactions
            """)

            date_range = cursor.fetchone()
            if not date_range or not date_range[0] or not date_range[1]:
                print("No transaction data available for analysis.")
                conn.close()
                return

            min_date, max_date = date_range
            print(f"Analyzing transactions from {min_date} to {max_date}")
        except sqlite3.OperationalError as e:
            print(f"Error reading from database: {e}")
            print("Please make sure you've imported transactions and consolidated them first.")
            print("Run: python src/app.py --consolidate")
            conn.close()
            return

        # Get spending by category for the last 3 months
        three_months_ago = (pd.to_datetime(max_date) - pd.DateOffset(months=3)).strftime('%Y-%m-%d')

        try:
            df_category = pd.read_sql_query("""
            SELECT category, SUM(amount) as total_spent
            FROM consolidated_transactions
            WHERE category IS NOT NULL
            AND category != ''
            AND date_posted >= ?
            AND amount < 0  -- Only expenses (negative amounts)
            GROUP BY category
            ORDER BY total_spent ASC  -- Ascending because expenses are negative
            LIMIT 10
            """, conn, params=(three_months_ago,))

            # Get spending by month
            df_monthly = pd.read_sql_query("""
            SELECT
                strftime('%Y-%m', date_posted) as month,
                SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) as expenses,
                SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as income
            FROM consolidated_transactions
            GROUP BY strftime('%Y-%m', date_posted)
            ORDER BY month DESC
            LIMIT 6
            """, conn)

            # Get recurring expenses
            df_recurring = pd.read_sql_query("""
            SELECT description, category, AVG(amount) as avg_amount, COUNT(*) as occurrence_count
            FROM consolidated_transactions
            WHERE amount < 0
            AND date_posted >= ?
            GROUP BY description, category
            HAVING COUNT(*) >= 3
            ORDER BY avg_amount ASC
            LIMIT 10
            """, conn, params=(three_months_ago,))
        except (sqlite3.OperationalError, pd.errors.DatabaseError) as e:
            print(f"Error analyzing transactions: {e}")
            print("There may be a problem with the database structure or data.")
            conn.close()
            return

        conn.close()

        # Display insights

        # Top spending categories
        if not df_category.empty:
            print("\n🔍 Top spending categories (last 3 months):")
            for i, row in df_category.iterrows():
                print(f"  {row['category']:<20} ${abs(row['total_spent']):.2f}")

        # Monthly spending trends
        if not df_monthly.empty:
            print("\n📊 Monthly spending trends:")
            print(f"{'Month':<10} {'Income':<12} {'Expenses':<12} {'Net':<12}")
            print("-" * 50)

            for i, row in df_monthly.iterrows():
                month = row['month']
                income = row['income']
                expenses = abs(row['expenses'])
                net = income + row['expenses']  # expenses are negative

                print(f"{month:<10} ${income:<10.2f} ${expenses:<10.2f} ${net:<10.2f}")

        # Recurring expenses
        if not df_recurring.empty:
            print("\n🔄 Recurring expenses:")
            for i, row in df_recurring.iterrows():
                desc = (row['description'][:30] + "...") if len(row['description']) > 33 else row['description']
                category = row['category'] if row['category'] else 'Uncategorized'
                print(f"  {desc:<33} ${abs(row['avg_amount']):.2f}/month ({category})")

        # Provide recommendations
        print("\n💡 Recommendations:")

        # Recommend budget adjustments based on spending patterns
        if not df_category.empty:
            max_category = df_category.iloc[0]
            print(f"• Your highest spending category is {max_category['category']} (${abs(max_category['total_spent']):.2f}).")
            print(f"  Consider setting a budget limit for this category.")

        # Identify potential savings from recurring expenses
        if not df_recurring.empty and len(df_recurring) > 3:
            recurring_total = abs(df_recurring['avg_amount'].sum())
            print(f"• You have {len(df_recurring)} recurring expenses totaling ~${recurring_total:.2f}/month.")
            print(f"  Reviewing these subscriptions could yield potential savings.")

        # Check income vs expenses trend
        if not df_monthly.empty and len(df_monthly) >= 3:
            recent_months = df_monthly.head(3)
            avg_net = (recent_months['income'] + recent_months['expenses']).mean()

            if avg_net < 0:
                print(f"• Warning: Your average monthly spending exceeds income by ${abs(avg_net):.2f}.")
                print(f"  Consider reducing expenses or finding additional income sources.")
            elif avg_net > 0:
                print(f"• Good job! You're saving an average of ${avg_net:.2f} per month.")
                print(f"  Consider allocating this to your savings goals.")

    # ---------------------------
    # Machine Learning and Classification
    # ---------------------------

    def get_classifier_dataset(db_path: str) -> Tuple[Optional[pd.Series], Optional[pd.Series]]:
        """
        Extract dataset for training the rental expense classifier.

        Args:
            db_path: Path to the SQLite database

        Returns:
            X: List of transaction descriptions
            y: List of labels (1 for rental, 0 for non-rental)
        """
        conn = sqlite3.connect(db_path)

        # Get all classified transactions
        query = """
        SELECT description, category, source, amount, rental_related
        FROM consolidated_transactions
        WHERE rental_related IS NOT NULL
        """

        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            print("No classified transactions found. Please classify some transactions first.")
            return None, None

        # Prepare features and target
        X = df['description'].fillna('').astype(str)
        y = df['rental_related'].astype(int)

        print(f"Dataset prepared: {len(X)} transactions ({sum(y)} rental, {len(y) - sum(y)} non-rental)")

        return X, y


    def train_rental_classifier(db_path: str, model_dir: str) -> Optional[Pipeline]:
        """
        Train a machine learning model to classify transactions as rental-related.

        Args:
            db_path: Path to the SQLite database
            model_dir: Directory to save the trained model

        Returns:
            The trained model and accuracy metrics
        """
        # Create model dir if it doesn't exist
        os.makedirs(model_dir, exist_ok=True)

        # Get training data
        X, y = get_classifier_dataset(db_path)
        if X is None or len(X) < 10:
            print("Not enough data to train a model. Please classify more transactions.")
            return None

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)

        # Create a pipeline with TF-IDF and RandomForest
        pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(
                min_df=2, max_df=0.8,
                ngram_range=(1, 2),  # Use unigrams and bigrams
                stop_words='english'
            )),
            ('classifier', RandomForestClassifier(
                n_estimators=100,
                class_weight='balanced',
                random_state=42
            ))
        ])

        # Train model
        print("Training rental expense classifier...")
        pipeline.fit(X_train, y_train)

        # Evaluate
        y_pred = pipeline.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred)

        print(f"Model accuracy: {accuracy:.2f}")
        print("\nClassification Report:")
        print(report)

        # Save model
        model_path = os.path.join(model_dir, f"rental_classifier_{datetime.datetime.now().strftime('%Y%m%d')}.joblib")
        joblib.dump(pipeline, model_path)
        print(f"Model saved to: {model_path}")

        # Also save as latest model
        latest_model_path = os.path.join(model_dir, "latest_rental_classifier.joblib")
        joblib.dump(pipeline, latest_model_path)

        return pipeline


    def get_latest_model(model_dir: str) -> Optional[Pipeline]:
        """
        Get the most recently trained model.

        Args:
            model_dir: Directory where models are stored

        Returns:
            Most recent trained model
        """
        latest_model_path = os.path.join(model_dir, "latest_rental_classifier.joblib")
        if os.path.exists(latest_model_path):
            return joblib.load(latest_model_path)
        return None


    def batch_predict_rentals(db_path: str, model_dir: str, limit: int = 100) -> None:
        """
        Use ML model to predict rental classification for unclassified transactions.

        Args:
            db_path: Path to the SQLite database
            model_dir: Directory where models are stored
            limit: Maximum number of transactions to process
        """
        # Load the model
        model = get_latest_model(model_dir)
        if model is None:
            print("No trained model found. Please train a model first.")
            return

        conn = sqlite3.connect(db_path)

        # Get unclassified transactions
        query = f"""
        SELECT id, description, category, source, amount
        FROM consolidated_transactions
        WHERE rental_related IS NULL
        LIMIT {limit}
        """

        df = pd.read_sql_query(query, conn)

        if df.empty:
            print("No unclassified transactions found.")
            conn.close()
            return

        # Make predictions
        print(f"Making predictions for {len(df)} transactions...")
        predictions = model.predict(df['description'].fillna('').astype(str))
        probabilities = model.predict_proba(df['description'].fillna('').astype(str))

        # Add predictions to dataframe
        df['rental_predicted'] = predictions
        df['confidence'] = [max(prob) for prob in probabilities]

        # Show predictions
        print("\nPredictions (showing top 10 with highest confidence):")
        print(f"{'ID':<5} {'Confidence':<10} {'Rental':<6} {'Description':<50}")
        print("-" * 80)

        # Sort by confidence
        df_sorted = df.sort_values('confidence', ascending=False)

        for i, row in df_sorted.head(10).iterrows():
            rental = "Yes" if row['rental_predicted'] == 1 else "No"
            desc = row['description'][:47] + "..." if len(row['description']) > 50 else row['description']
            print(f"{row['id']:<5} {row['confidence']:.2f}      {rental:<6} {desc:<50}")

        # Ask if we should apply predictions
        apply = input("\nApply predictions to database? (y/n): ").strip().lower()
        if apply == 'y':
            cursor = conn.cursor()
            count = 0

            # Only apply high-confidence predictions
            confidence_threshold = 0.7

            for i, row in df_sorted.iterrows():
                if row['confidence'] >= confidence_threshold:
                    cursor.execute("""
                        UPDATE consolidated_transactions
                        SET rental_related = ?
                        WHERE id = ?
                    """, (int(row['rental_predicted']), row['id']))
                    count += 1

            conn.commit()
            print(f"\nApplied {count} high-confidence predictions (threshold: {confidence_threshold})")

        conn.close()
