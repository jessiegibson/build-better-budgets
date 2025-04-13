You are tasked with building a web application to manage personal finances with advanced budgeting, forecasting, and tax optimization capabilities. The application should:

1. **Ingest Financial Data:**

   - Support importing transactions from CSV, PDF, and QFX files.
   - Automatically detect and map transaction sources from any financial institution.
   - Standardize transaction data across various formats and sources.

2. **Transaction Consolidation & Management:**

   - Incrementally import transactions to avoid duplicates.
   - Maintain a detailed import history log.
   - Consolidate all transactions into a unified database using DuckDb or SQLite.

3. **Machine Learning & Classification:**

   - Utilize machine learning algorithms (Random Forest with TF-IDF) to classify transactions into categories like rental-related expenses, recurring payments, subscriptions, and tax-deductible expenses.
   - Provide an interactive user interface for training ML models by manually classifying transaction samples.
   - Predict transaction classifications automatically with configurable batch sizes.

4. **Budgeting & Forecasting:**

   - Allow users to create detailed monthly and annual budgets.
   - Forecast future expenses based on historical transaction patterns and recurring payments.
   - Optimize cash flow management through predictive insights.

5. **Rental Property & Tax Deduction Management:**

   - Distinguish between property maintenance (immediate deduction) and upgrades (depreciation over 28.5 years).
   - Track Section 179 deductions and standard depreciation schedules for business equipment.
   - Generate comprehensive tax reports, including itemized deductions and depreciation schedules.

6. **Web Interface Features:**

   - Dashboard summarizing key financial metrics.
   - Transaction management interface (search, filter, classify).
   - Budget creation and monitoring.
   - Financial goal setting and tracking.
   - Cash flow forecasting visualization.
   - Interactive tools for tax deductions and depreciation management.

7. **The Technical Stack:**

   - The application is currently built in Python using Flask for the web application.&#x20;
   - Using SKLearn for the machine learning, prediction, and classification. 

Build upon the existing CLI (`src/app.py`) and web application (`src/ui.py`) by implementing these comprehensive features within an intuitive, user-friendly web interface.

