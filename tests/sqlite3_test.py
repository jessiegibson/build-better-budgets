import sqlite3


def test_db_contents(db_path):
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
                

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    if not tables:
        print("No tables found in the database.")

    else:
        print("Tables in the database:")
        for table in tables:
            print(table)
            table_name = table[0]
            print(f"\nTable: {table_name}")
            

            cursor.execute(f"PRAGMA table_info('{table_name}');")
            schema = cursor.fetchall()
            if schema:
                    print("Schema:")
                    for column in schema:
                        cid, name, col_type, notnull, dflt_value,pk=column
                        print(f" CID: {cid}, Columns: {name}, Type: {col_type}, NotNull: {bool(notnull)}, Default: {dflt_value}, Primary Key: {bool(pk)}")
            else:
                    print("No Schema information available!")


            cursor.execute(f'SELECT * FROM "{table_name}" LIMIT 5;')
            
            rows = cursor.fetchall()

            if rows:
                print("First 5 rows:")
                for row in rows:
                    print(row)

            else:
                print("The table is empty")

    conn.close()


db_path = "/Users/jag/workspace/github.com/jessiegibson/budgeting-app//db/transactions.db"
test_db_contents(db_path)


