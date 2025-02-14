import pymysql
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# MySQL Connection Details from .env
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
DB_PORT = int(os.getenv('DB_PORT', 3306))

def connect_to_database():
    """Connect to MySQL database."""
    try:
        return pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
    except Exception as e:
        print(f"❌ MySQL Connection Error: {e}")
        return None

def migrate_table():
    """Migrate portfolio_holdings table to use date as primary key."""
    connection = connect_to_database()
    if not connection:
        return

    try:
        with connection.cursor() as cursor:
            # First, verify that date column has no duplicates
            cursor.execute("SELECT date, COUNT(*) as count FROM portfolio_holdings GROUP BY date HAVING count > 1")
            duplicates = cursor.fetchall()
            if duplicates:
                print("Found duplicate dates. Please resolve these before proceeding:")
                for dup in duplicates:
                    print(f"Date: {dup['date']}, Count: {dup['count']}")
                return

            # Remove primary key from id and add it to date
            print("Modifying table structure...")
            cursor.execute("""
                ALTER TABLE portfolio_holdings 
                DROP PRIMARY KEY,
                DROP COLUMN id,
                ADD PRIMARY KEY (date)
            """)
            
            connection.commit()
            print("Successfully migrated portfolio_holdings table to use date as primary key")
            
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        connection.close()

if __name__ == "__main__":
    print("Starting database migration...")
    migrate_table()
    print("Migration completed.")