from datetime import datetime, timedelta
import asyncio
import requests
from bs4 import BeautifulSoup
import pymysql
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# MySQL database connection details
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
DB_PORT = int(os.getenv('DB_PORT', 3306))

# Ensure the correct event loop policy for Windows
if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Target URL
URL = "https://treasuries.bitbo.io/"

def connect_to_database():
    """Connect to the MySQL database."""
    try:
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        return connection
    except Exception as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def initialize_database():
    """Create the necessary table if it doesn't exist."""
    connection = connect_to_database()
    if not connection:
        return

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bitcoin_holdings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    company_name VARCHAR(255) NOT NULL,
                    btc DECIMAL(20, 8) NOT NULL,
                    value DECIMAL(20, 8) NOT NULL,
                    date DATE NOT NULL
                )
            """)
            connection.commit()
            print("Table `bitcoin_holdings` ensured.")
    finally:
        connection.close()

def fetch_data_with_requests():
    """Fetch HTML content using requests."""
    try:
        print("Fetching page content...")
        response = requests.get(URL)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching the page: {e}")
        return None

def extract_specific_data(html_content):
    """Extract specific data from the HTML content."""
    if not html_content:
        print("No HTML content to parse.")
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    tables = soup.find_all("table", class_="treasuries-table")
    if len(tables) < 3:
        print("Not enough tables found in the HTML.")
        return []

    table = tables[2]
    print("Correct table found! Extracting data...")
    tbody = table.find("tbody")
    rows = tbody.find_all("tr")[:3]
    extracted_data = []
    for row in rows:
        company_name = row.find("td", class_="td-company").get_text(strip=True)

        if company_name == "Marathon Digital Holdings Inc":
            company_name = "Marathon Digital"

        btc = row.find("td", class_="td-company_btc").get_text(strip=True).replace(',', '')
        value = row.find("td", class_="td-value").get_text(strip=True).replace(',', '').replace('$', '')

        extracted_data.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "company_name": company_name,
            "btc": float(btc),
            "value": float(value) / 1e6  # Convert to millions
        })

    return extracted_data

def save_data_to_mysql(data):
    """Save extracted data to the MySQL database."""
    connection = connect_to_database()
    if not connection:
        return

    today_date = datetime.now().strftime("%Y-%m-%d")
    try:
        with connection.cursor() as cursor:
            for entry in data:
                # Check if data already exists for today
                cursor.execute("""
                    SELECT * FROM bitcoin_holdings
                    WHERE company_name = %s AND date = %s
                """, (entry["company_name"], today_date))
                existing_entry = cursor.fetchone()

                if not existing_entry:
                    # Insert new data
                    cursor.execute("""
                        INSERT INTO bitcoin_holdings (company_name, btc, value, date)
                        VALUES (%s, %s, %s, %s)
                    """, (entry["company_name"], entry["btc"], entry["value"], entry["date"]))
            connection.commit()
            print("Data saved to MySQL.")
    finally:
        connection.close()

def load_data_from_mysql():
    """Fetch yesterday's BTC data from MySQL."""
    conn = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        port=DB_PORT,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )
    cursor = conn.cursor()

    # Get yesterday's date
    date_yesterday = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Query for yesterday's data
    query = """
        SELECT company_name, btc, date 
        FROM bitcoin_holdings 
        WHERE date = %s;
    """
    cursor.execute(query, (date_yesterday,))

    data = cursor.fetchall()
    conn.close()

    if not data:
        print(f"⚠️ No data found for {date_yesterday} in the database.")

    return data

def calculate_daily_change(new_data, old_data, date_today, date_yesterday):
    """Compare today's BTC holdings with exactly yesterday's BTC holdings."""
    changes = []

    # Create a dictionary for easy lookup (company_name -> BTC on yesterday's date)
    yesterday_btc_dict = {}
    for item in old_data:
        company = item["company_name"]
        yesterday_btc_dict[company] = float(item["btc"])  # Store BTC from yesterday

    for new in new_data:
        company_name = new["company_name"]
        new_btc = float(new["btc"])  # Today's BTC

        # Get yesterday's BTC value if available
        old_btc = yesterday_btc_dict.get(company_name, None)

        if old_btc is not None:
            change = new_btc - old_btc
        else:
            change = "Not Available"  # No BTC data for yesterday

        changes.append({
            "company_name": company_name,
            "btc_today": new_btc,
            "btc_yesterday": old_btc if old_btc is not None else "Not Available",
            "daily_change": change
        })

    return changes

def calculate_monthly_change(new_data, old_data):
    """Calculate 30-day BTC quantity change."""
    changes = []
    for new in new_data:
        total_change = 0
        for i in range(1, 31):
            period_ago_date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            old_entry = next((item for item in old_data if item["company_name"] == new["company_name"] and item["date"] == period_ago_date), None)
            if old_entry:
                # Convert `old_entry["btc"]` to float for arithmetic operations
                total_change += new["btc"] - float(old_entry["btc"])
        changes.append({
            "company_name": new["company_name"],
            "monthly_change": total_change if total_change != 0 else "Shown after 1 month"
        })
    return changes

def generate_changes_table(new_data, daily_changes=None, monthly_changes=None):
    """Generate formatted table string (based on BTC quantity)."""
    if not new_data:
        print("No new data provided to generate the table.")
        return None

    header_format = "{:<20}  {:<15}  {:<15}  {:<15}"
    row_format = "{:<20}  {:<15}  {:<15}  {:<15}"

    table = header_format.format("Company", "BTC Held", "Yesterday", "Last Month") + "\n"
    table += "-" * 76 + "\n"
    for new in new_data:
        daily_change = next((c["daily_change"] for c in (daily_changes or []) if c["company_name"] == new["company_name"]), None)
        monthly_change = next((c["monthly_change"] for c in (monthly_changes or []) if c["company_name"] == new["company_name"]), None)

        # Get today's date and weekday
        today = datetime.now()
        weekday = today.strftime("%A")  # Monday, Tuesday, etc.

        # Handle missing daily change data
        if daily_change is None:
            if weekday in ["Saturday", "Sunday"]:
                daily_change_str = "No Data (Weekend)"
            else:
                daily_change_str = "No Previous Data"
        else:
            daily_change_str = f"{daily_change:.2f}" if isinstance(daily_change, float) else daily_change

        # Handle missing monthly change data
        monthly_change_str = f"{monthly_change:.2f}" if isinstance(monthly_change, float) else "Shown after 1 month"

        latest_btc_str = f"{new['btc']}"
        table += row_format.format(new["company_name"], latest_btc_str, daily_change_str, monthly_change_str) + "\n"

    return table

def get_chain():
    # Ensure the database is ready
    initialize_database()

    # Fetch and process data
    html_content = fetch_data_with_requests()
    if not html_content:
        return "Failed to fetch data."

    new_data = extract_specific_data(html_content)
    old_data = load_data_from_mysql()

    # Save new data to MySQL
    save_data_to_mysql(new_data)

    # Determine today's and yesterday's dates
    date_today = datetime.today().strftime("%Y-%m-%d")
    date_yesterday = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Calculate daily and monthly changes
    daily_changes = calculate_daily_change(new_data, old_data, date_today, date_yesterday) if old_data else []
    monthly_changes = calculate_monthly_change(new_data, old_data) if old_data else []

    # Generate the changes table
    table = generate_changes_table(new_data, daily_changes, monthly_changes)
    if table:
        msg = f"📖 *Bitcoin Public Company*\n"
        msg += "```\n"
        msg += table
        msg += "```"
        return msg

    return "No data available."

if __name__ == "__main__":
    # For testing purposes
    print(get_chain())