"""
Machine Learning Classifier Module

Provides functionality for training and using machine learning models
to automatically classify transactions based on user-provided training data.
"""

import os
import numpy as np
import pandas as pd
import sqlite3
import logging
import joblib
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Union

# ML libraries
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report, accuracy_score, precision_score, recall_score, f1_score

# Import local modules
from src.data_ingestion import get_db_connection

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models')
CATEGORIES_FILE = os.path.join(MODELS_DIR, 'valid_categories.txt')

class TransactionClassifier:
    """
    A machine learning classifier for financial transactions.
    
    Can be trained to classify transactions into various categories based on:
    - Rental-related
    - Expense categories
    - Recurring payments
    - Subscription services
    - Tax-deductible expenses
    - Equipment/tools for depreciation
    """
    
    def __init__(self, classification_type: str = "category"):
        """
        Initialize a transaction classifier for a specific classification type.
        
        Args:
            classification_type: Type of classification to perform (category, 
                rental, recurring, subscription, tax, equipment)
        """
        self.classification_type = classification_type
        self.model = None
        self.pipeline = None
        self.classes = None
        self.vectorizer = None
        self.confidence_threshold = 0.6  # Default confidence threshold
        
        # Ensure models directory exists
        os.makedirs(MODELS_DIR, exist_ok=True)
        
        # Map classification types to database columns and model file prefixes
        self.type_mapping = {
            "category": {
                "column": "expense_category",
                "model_prefix": "category_classifier",
                "multi_class": True
            },
            "rental": {
                "column": "rental_related",
                "model_prefix": "rental_classifier",
                "multi_class": False
            },
            "recurring": {
                "column": "recurring",
                "model_prefix": "recurring_classifier",
                "multi_class": False
            },
            "subscription": {
                "column": "subscription",
                "model_prefix": "subscription_classifier",
                "multi_class": False
            },
            "tax": {
                "column": "tax_deductible",
                "model_prefix": "tax_classifier",
                "multi_class": False
            },
            "equipment": {
                "column": "equipment_tools",
                "model_prefix": "equipment_classifier",
                "multi_class": False
            }
        }
        
        # Validate classification type
        if classification_type not in self.type_mapping:
            raise ValueError(f"Invalid classification type: {classification_type}. "
                            f"Must be one of {list(self.type_mapping.keys())}")
        
        # Try to load existing model if available
        self.load_latest_model()
    
    def load_latest_model(self) -> bool:
        """
        Load the latest model for the current classification type.
        
        Returns:
            True if a model was loaded, False otherwise
        """
        prefix = self.type_mapping[self.classification_type]["model_prefix"]
        
        # Look for model files with the appropriate prefix
        model_files = [f for f in os.listdir(MODELS_DIR) 
                     if f.startswith(prefix) and f.endswith('.joblib')]
        
        if not model_files:
            logger.info(f"No existing models found for {self.classification_type} classification")
            return False
        
        # Find the most recent model file
        latest_model = sorted(model_files)[-1]
        model_path = os.path.join(MODELS_DIR, latest_model)
        
        try:
            # Load the model
            self.pipeline = joblib.load(model_path)
            
            # Extract components from pipeline
            self.vectorizer = self.pipeline.named_steps['vectorizer']
            self.model = self.pipeline.named_steps['classifier']
            
            # Get classes
            self.classes = self.model.classes_
            
            logger.info(f"Loaded model from {model_path}")
            return True
        except Exception as e:
            logger.error(f"Error loading model from {model_path}: {e}")
            return False
    
    def save_model(self) -> str:
        """
        Save the current model to a file.
        
        Returns:
            Path to the saved model file
        """
        if self.pipeline is None:
            raise ValueError("No model to save")
        
        # Create a timestamp-based filename
        timestamp = datetime.now().strftime("%Y%m%d")
        prefix = self.type_mapping[self.classification_type]["model_prefix"]
        filename = f"{prefix}_{timestamp}.joblib"
        filepath = os.path.join(MODELS_DIR, filename)
        
        # Save the pipeline
        joblib.dump(self.pipeline, filepath)
        
        # Also save as latest model
        latest_path = os.path.join(MODELS_DIR, f"latest_{prefix}.joblib")
        joblib.dump(self.pipeline, latest_path)
        
        logger.info(f"Saved model to {filepath}")
        return filepath
    
    def get_training_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get training data from the database for the current classification type.
        
        Returns:
            Tuple of (X, y) where X is the feature data and y is the target labels
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        
        column = self.type_mapping[self.classification_type]["column"]
        multi_class = self.type_mapping[self.classification_type]["multi_class"]
        
        # Query for classified transactions
        if multi_class:
            query = f"""
                SELECT description, {column}
                FROM consolidated_transactions
                WHERE {column} IS NOT NULL AND {column} != ''
            """
        else:
            query = f"""
                SELECT description, {column}
                FROM consolidated_transactions
                WHERE {column} IS NOT NULL
            """
        
        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            logger.warning(f"No training data found for {self.classification_type} classification")
            return np.array([]), np.array([])
        
        # Prepare X and y
        X_text = []
        y = []
        
        for row in results:
            description = row['description']
            label = row[column]
            
            # Skip empty descriptions
            if not description:
                continue
                
            X_text.append(description)
            y.append(label)
        
        X = np.array(X_text)
        y = np.array(y)
        
        logger.info(f"Got {len(X)} training examples for {self.classification_type} classification")
        
        # If binary classification, convert labels to 0/1
        if not multi_class:
            y = y.astype(int)
        
        # If multiclass, save valid categories list
        if multi_class:
            self._save_valid_categories(list(set(y)))
        
        return X, y
    
    def _save_valid_categories(self, categories: List[str]) -> None:
        """
        Save the list of valid categories to a file.
        
        Args:
            categories: List of valid category names
        """
        # Sort categories for consistency
        categories = sorted(categories)
        
        with open(CATEGORIES_FILE, 'w') as f:
            for category in categories:
                f.write(f"{category}\n")
        
        logger.info(f"Saved {len(categories)} valid categories to {CATEGORIES_FILE}")
    
    def train_model(self) -> Dict[str, float]:
        """
        Train a model using data from the database.
        
        Returns:
            Dictionary of evaluation metrics
        """
        X, y = self.get_training_data()
        
        if len(X) == 0 or len(y) == 0:
            raise ValueError("No training data available")
        
        # Split into train/test sets
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        logger.info(f"Training model with {len(X_train)} examples")
        
        # Create a TF-IDF vectorizer for text features
        vectorizer = TfidfVectorizer(
            max_features=5000,
            min_df=2,
            ngram_range=(1, 2),
            sublinear_tf=True
        )
        
        # Create a classifier
        multi_class = self.type_mapping[self.classification_type]["multi_class"]
        
        if multi_class:
            clf = RandomForestClassifier(
                n_estimators=100, 
                max_depth=None,
                n_jobs=-1,
                random_state=42
            )
        else:
            # For binary classification, use class weights to handle imbalance
            clf = RandomForestClassifier(
                n_estimators=100,
                max_depth=None,
                class_weight='balanced',
                n_jobs=-1,
                random_state=42
            )
        
        # Create a pipeline
        self.pipeline = Pipeline([
            ('vectorizer', vectorizer),
            ('classifier', clf)
        ])
        
        # Train the model
        self.pipeline.fit(X_train, y_train)
        
        # Extract components from pipeline
        self.vectorizer = self.pipeline.named_steps['vectorizer']
        self.model = self.pipeline.named_steps['classifier']
        self.classes = self.model.classes_
        
        # Evaluate the model
        y_pred = self.pipeline.predict(X_test)
        
        # Calculate metrics
        metrics = {}
        
        if multi_class:
            # For multiclass, use weighted metrics
            metrics['accuracy'] = accuracy_score(y_test, y_pred)
            metrics['precision'] = precision_score(y_test, y_pred, average='weighted', zero_division=0)
            metrics['recall'] = recall_score(y_test, y_pred, average='weighted', zero_division=0)
            metrics['f1'] = f1_score(y_test, y_pred, average='weighted', zero_division=0)
        else:
            # For binary, use binary metrics
            metrics['accuracy'] = accuracy_score(y_test, y_pred)
            metrics['precision'] = precision_score(y_test, y_pred, zero_division=0)
            metrics['recall'] = recall_score(y_test, y_pred, zero_division=0)
            metrics['f1'] = f1_score(y_test, y_pred, zero_division=0)
        
        # Save the model
        self.save_model()
        
        logger.info(f"Model trained with metrics: {metrics}")
        return metrics
    
    def predict(self, descriptions: List[str]) -> Tuple[List[Any], List[float]]:
        """
        Predict classifications for a list of transaction descriptions.
        
        Args:
            descriptions: List of transaction description strings
            
        Returns:
            Tuple of (predictions, confidence_scores)
        """
        if self.pipeline is None:
            raise ValueError("No trained model available")
        
        # Make predictions
        probas = self.pipeline.predict_proba(descriptions)
        
        # Get predicted classes and confidence scores
        predictions = []
        confidence_scores = []
        
        for proba in probas:
            # Get index of highest probability
            idx = np.argmax(proba)
            prediction = self.classes[idx]
            confidence = proba[idx]
            
            predictions.append(prediction)
            confidence_scores.append(confidence)
        
        return predictions, confidence_scores
    
    def classify_transaction(self, description: str) -> Tuple[Any, float]:
        """
        Classify a single transaction description.
        
        Args:
            description: Transaction description text
            
        Returns:
            Tuple of (prediction, confidence)
        """
        predictions, confidences = self.predict([description])
        return predictions[0], confidences[0]
    
    def batch_classify_transactions(self, limit: int = 100) -> int:
        """
        Classify a batch of unclassified transactions in the database.
        
        Args:
            limit: Maximum number of transactions to classify
            
        Returns:
            Number of transactions classified
        """
        if self.pipeline is None:
            raise ValueError("No trained model available")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        column = self.type_mapping[self.classification_type]["column"]
        
        # Query for unclassified transactions
        query = f"""
            SELECT id, description
            FROM consolidated_transactions
            WHERE ({column} IS NULL OR {column} = '' OR {column} = 0)
            LIMIT ?
        """
        
        cursor.execute(query, (limit,))
        results = cursor.fetchall()
        
        if not results:
            logger.info(f"No unclassified transactions found for {self.classification_type}")
            conn.close()
            return 0
        
        # Prepare descriptions
        ids = []
        descriptions = []
        
        for row in results:
            ids.append(row['id'])
            descriptions.append(row['description'])
        
        # Make predictions
        predictions, confidences = self.predict(descriptions)
        
        # Apply updates where confidence exceeds threshold
        updates = 0
        for i, (transaction_id, prediction, confidence) in enumerate(zip(ids, predictions, confidences)):
            if confidence >= self.confidence_threshold:
                # For binary classifications, cast to integer
                if not self.type_mapping[self.classification_type]["multi_class"]:
                    value = int(prediction)
                else:
                    value = prediction
                
                # Update the database
                cursor.execute(f"""
                    UPDATE consolidated_transactions
                    SET {column} = ?
                    WHERE id = ?
                """, (value, transaction_id))
                
                updates += 1
        
        conn.commit()
        conn.close()
        
        logger.info(f"Classified {updates}/{len(ids)} transactions with confidence >= {self.confidence_threshold}")
        return updates
    
    def set_confidence_threshold(self, threshold: float) -> None:
        """
        Set the confidence threshold for applying predictions.
        
        Args:
            threshold: Confidence threshold (0.0 to 1.0)
        """
        if threshold < 0.0 or threshold > 1.0:
            raise ValueError("Confidence threshold must be between 0.0 and 1.0")
        
        self.confidence_threshold = threshold
        logger.info(f"Set confidence threshold to {threshold}")

def batch_classification(classification_type: str, limit: int = 100) -> int:
    """
    Classify a batch of transactions for the specified classification type.
    
    Args:
        classification_type: Type of classification to perform
        limit: Maximum number of transactions to classify
        
    Returns:
        Number of transactions classified
    """
    classifier = TransactionClassifier(classification_type)
    
    # Check if model exists
    if classifier.pipeline is None:
        logger.warning(f"No trained model available for {classification_type} classification")
        return 0
    
    # Run classification
    return classifier.batch_classify_transactions(limit)

def get_similar_transactions(transaction_id: int, limit: int = 5) -> List[Dict]:
    """
    Find transactions similar to a given transaction.
    
    Args:
        transaction_id: ID of the transaction to find similar ones for
        limit: Maximum number of similar transactions to return
        
    Returns:
        List of similar transactions
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get the reference transaction
    cursor.execute("""
        SELECT description, amount
        FROM consolidated_transactions
        WHERE id = ?
    """, (transaction_id,))
    
    ref_transaction = cursor.fetchone()
    if not ref_transaction:
        conn.close()
        return []
    
    ref_description = ref_transaction['description']
    ref_amount = ref_transaction['amount']
    
    # Find similar transactions based on description (simple approach)
    # This could be improved with TF-IDF and cosine similarity
    words = ref_description.lower().split()
    
    # Generate a query that finds transactions containing at least some of the words
    if len(words) > 3:
        # If we have enough words, look for transactions with some word overlap
        search_clauses = []
        for word in words:
            if len(word) > 3:  # Only use words with > 3 chars
                search_clauses.append(f"description LIKE '%{word}%'")
        
        if search_clauses:
            where_clause = " OR ".join(search_clauses)
        else:
            where_clause = "1=0"  # No good words found
    else:
        # If short description, just search for similar text
        where_clause = f"description LIKE '%{ref_description[:10]}%'"
    
    # Find similar transactions
    query = f"""
        SELECT id, date_posted, description, amount, category, source
        FROM consolidated_transactions
        WHERE id != ? AND ({where_clause})
        ORDER BY ABS(amount - ?)  -- Order by similarity in amount
        LIMIT ?
    """
    
    cursor.execute(query, (transaction_id, ref_amount, limit))
    similar = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return similar

def detect_recurring_transactions(min_count: int = 2, time_window_months: int = 12) -> int:
    """
    Automatically detect recurring transactions in the database.
    
    Args:
        min_count: Minimum number of occurrences to consider recurring
        time_window_months: Time window (in months) to look for patterns
        
    Returns:
        Number of recurring groups detected
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # First, clear existing recurring groups
    cursor.execute("""
        UPDATE consolidated_transactions
        SET recurring_group = NULL
        WHERE recurring_group IS NOT NULL
    """)
    
    # Get date range for time window
    cursor.execute("""
        SELECT date(MAX(date_posted), '-' || ? || ' months') as start_date,
               MAX(date_posted) as end_date
        FROM consolidated_transactions
    """, (time_window_months,))
    
    date_range = cursor.fetchone()
    if not date_range or not date_range['start_date'] or not date_range['end_date']:
        conn.close()
        return 0
    
    # Get transactions within the time window, with amount < 0 (expenses only)
    cursor.execute("""
        SELECT id, description, date_posted, amount, source
        FROM consolidated_transactions
        WHERE date_posted BETWEEN ? AND ?
            AND amount < 0
        ORDER BY ABS(amount), description
    """, (date_range['start_date'], date_range['end_date']))
    
    transactions = [dict(row) for row in cursor.fetchall()]
    
    # Group similar transactions
    groups = []
    processed_ids = set()
    
    for i, txn in enumerate(transactions):
        if txn['id'] in processed_ids:
            continue
        
        # Start a new group
        group = [txn]
        processed_ids.add(txn['id'])
        
        # Find similar transactions
        for j in range(i + 1, len(transactions)):
            other = transactions[j]
            if other['id'] in processed_ids:
                continue
                
            # Check if similar
            amount_diff = abs(txn['amount'] - other['amount'])
            amount_pct_diff = amount_diff / abs(txn['amount']) if txn['amount'] != 0 else float('inf')
            
            # Define similarity criteria
            similar_amount = amount_pct_diff < 0.05  # Within 5% of amount
            similar_desc = False
            
            # Check for similar description
            if len(txn['description']) > 5 and len(other['description']) > 5:
                # Look for common prefix or suffix
                desc1 = txn['description'].lower()
                desc2 = other['description'].lower()
                
                # Check for common prefix (first 10 chars)
                prefix_len = min(10, len(desc1), len(desc2))
                if desc1[:prefix_len] == desc2[:prefix_len]:
                    similar_desc = True
                    
                # Check for common words
                words1 = set(desc1.split())
                words2 = set(desc2.split())
                common_words = words1.intersection(words2)
                
                if len(common_words) >= 2 and len(common_words) / min(len(words1), len(words2)) > 0.5:
                    similar_desc = True
            
            if similar_amount and similar_desc:
                group.append(other)
                processed_ids.add(other['id'])
        
        # If we found enough occurrences, consider it a recurring group
        if len(group) >= min_count:
            groups.append(group)
    
    # Update the database with recurring groups
    for group_id, group in enumerate(groups):
        group_id_str = f"recurring_group_{group_id}"
        
        # Detect frequency
        if len(group) >= 2:
            # Sort by date
            group.sort(key=lambda x: x['date_posted'])
            
            # Calculate average interval in days
            intervals = []
            for i in range(1, len(group)):
                date1 = datetime.strptime(group[i-1]['date_posted'], '%Y-%m-%d')
                date2 = datetime.strptime(group[i]['date_posted'], '%Y-%m-%d')
                interval = (date2 - date1).days
                intervals.append(interval)
            
            avg_interval = sum(intervals) / len(intervals)
            
            # Determine frequency
            if avg_interval <= 10:
                frequency = "WEEKLY"
            elif avg_interval <= 40:
                frequency = "MONTHLY"
            elif avg_interval <= 100:
                frequency = "QUARTERLY"
            else:
                frequency = "YEARLY"
        else:
            frequency = None
        
        # Update all transactions in the group
        for txn in group:
            cursor.execute("""
                UPDATE consolidated_transactions
                SET recurring = 1,
                    recurring_group = ?,
                    recurring_freq = ?
                WHERE id = ?
            """, (group_id_str, frequency, txn['id']))
    
    conn.commit()
    
    # Now add to recurring_forecasts table for future months
    cursor.execute("DELETE FROM recurring_forecasts")
    
    # For each recurring group, add a forecast
    for group_id, group in enumerate(groups):
        group_id_str = f"recurring_group_{group_id}"
        
        # Get the latest transaction in the group
        latest = max(group, key=lambda x: x['date_posted'])
        
        # Calculate next date based on frequency
        latest_date = datetime.strptime(latest['date_posted'], '%Y-%m-%d')
        frequency = None
        
        # Get the frequency from the DB
        cursor.execute("""
            SELECT recurring_freq 
            FROM consolidated_transactions 
            WHERE recurring_group = ? 
            LIMIT 1
        """, (group_id_str,))
        
        freq_result = cursor.fetchone()
        if freq_result:
            frequency = freq_result['recurring_freq']
        
        if frequency == "WEEKLY":
            next_date = latest_date.replace(day=latest_date.day + 7)
        elif frequency == "MONTHLY":
            month = latest_date.month + 1
            year = latest_date.year
            if month > 12:
                month = 1
                year += 1
            next_date = latest_date.replace(year=year, month=month)
        elif frequency == "QUARTERLY":
            month = latest_date.month + 3
            year = latest_date.year
            if month > 12:
                month = month - 12
                year += 1
            next_date = latest_date.replace(year=year, month=month)
        elif frequency == "YEARLY":
            next_date = latest_date.replace(year=latest_date.year + 1)
        else:
            # Default to monthly if frequency not determined
            month = latest_date.month + 1
            year = latest_date.year
            if month > 12:
                month = 1
                year += 1
            next_date = latest_date.replace(year=year, month=month)
        
        # Calculate average amount
        avg_amount = sum(t['amount'] for t in group) / len(group)
        
        # Get most common category
        categories = {}
        for t in group:
            cursor.execute("""
                SELECT expense_category
                FROM consolidated_transactions
                WHERE id = ?
            """, (t['id'],))
            
            cat_result = cursor.fetchone()
            if cat_result and cat_result['expense_category']:
                cat = cat_result['expense_category']
                categories[cat] = categories.get(cat, 0) + 1
        
        if categories:
            category = max(categories.items(), key=lambda x: x[1])[0]
        else:
            category = None
        
        # Add to recurring_forecasts
        cursor.execute("""
            INSERT INTO recurring_forecasts
            (description, amount, frequency, next_date, category, source, recurring_group, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            latest['description'],
            avg_amount,
            frequency,
            next_date.strftime('%Y-%m-%d'),
            category,
            latest['source'],
            group_id_str,
            f"Based on {len(group)} past transactions"
        ))
    
    conn.commit()
    conn.close()
    
    logger.info(f"Detected {len(groups)} recurring transaction groups")
    return len(groups)

if __name__ == "__main__":
    print("Machine Learning Classifier Module")
    
    # Example: Train a category classifier
    print("\nTraining category classifier...")
    classifier = TransactionClassifier("category")
    try:
        metrics = classifier.train_model()
        print(f"Training metrics: {metrics}")
    except ValueError as e:
        print(f"Error: {e}")
    
    # Example: Detect recurring transactions
    print("\nDetecting recurring transactions...")
    recurring_count = detect_recurring_transactions()
    print(f"Detected {recurring_count} recurring transaction groups")
    
    # Example: Classify transactions
    print("\nClassifying unclassified transactions...")
    classified_count = classifier.batch_classify_transactions(500)
    print(f"Classified {classified_count} transactions")