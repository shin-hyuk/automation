import time
import random
import pymysql
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
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

# **Target URL**
URL = "https://intel.arkm.com/explorer/entity/worldlibertyfi"


# **Rotating User Agents**
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/110.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
]

# **✅ Target Assets**
TARGET_ASSETS = {"ETH", "WBTC", "STETH", "USDC", "TRX", "LINK", "AAVE", "ENA", "WETH"}

# **📌 Connect to MySQL**
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

# **📌 Initialize Database**
def initialize_database():
    connection = connect_to_database()
    if not connection:
        return

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_holdings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    date DATE NOT NULL,
                    asset_symbol VARCHAR(10) NOT NULL,
                    amount FLOAT NOT NULL,
                    total_value VARCHAR(20) NOT NULL
                )
            """)
            connection.commit()
            print("✅ Table `portfolio_holdings` is ready.")
    finally:
        connection.close()

# **📌 Fetch Data with Selenium**
def fetch_data_with_firefox():
    options = webdriver.FirefoxOptions()
    options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
    options.add_argument("--headless")

    driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()), options=options)

    try:
        print("🚀 Launching Firefox Browser...")
        driver.get(URL)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CLASS_NAME, "Portfolio_holdingsContainer__XyaUq"))
        )
        time.sleep(5)

        print("✅ Page Loaded. Extracting content...")
        return driver.page_source
    except Exception as e:
        print(f"❌ Firefox Error: {e}")
        return None
    finally:
        driver.quit()

# **📌 Extract Data**
def extract_holdings_and_value(html_content):
    if not html_content:
        print("❌ No HTML content to parse.")
        return None, None

    soup = BeautifulSoup(html_content, "html.parser")

    total_value_element = soup.find("span", class_="Header_portfolioValue__AemOW")
    total_value = total_value_element.get_text(strip=True) if total_value_element else "N/A"

    holdings_data = {}
    holdings_containers = soup.find_all("div", class_="Portfolio_holdingsContainer__XyaUq")

    for container in holdings_containers:
        try:
            amount_span = container.find("span")
            amount_text = amount_span.get_text(strip=True).replace("K", "000") if amount_span else "N/A"

            symbol_span = container.find("span", class_="Portfolio_holdingsSymbol__uOpkQ")
            symbol = symbol_span.get_text(strip=True) if symbol_span else "N/A"

            if symbol in TARGET_ASSETS:
                holdings_data[symbol] = float(amount_text.replace(",", ""))
        except Exception as e:
            print(f"⚠️ Skipping row due to error: {e}")

    return holdings_data, total_value

# **📌 Save Data to MySQL**
def save_data_to_mysql(holdings_data, total_value):
    connection = connect_to_database()
    if not connection:
        return

    today_date = datetime.now().strftime("%Y-%m-%d")
    try:
        with connection.cursor() as cursor:
            for asset, amount in holdings_data.items():
                cursor.execute("""
                    SELECT * FROM portfolio_holdings WHERE asset_symbol = %s AND date = %s
                """, (asset, today_date))
                existing_entry = cursor.fetchone()

                if not existing_entry:
                    cursor.execute("""
                        INSERT INTO portfolio_holdings (date, asset_symbol, amount, total_value)
                        VALUES (%s, %s, %s, %s)
                    """, (today_date, asset, amount, total_value))
            connection.commit()
            print("✅ Data saved to MySQL.")
    finally:
        connection.close()

# **📌 Load Data for Comparison**
def load_data_from_mysql():
    connection = connect_to_database()
    if not connection:
        return []

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM portfolio_holdings ORDER BY date DESC")
            return cursor.fetchall()
    finally:
        connection.close()

# **📌 Calculate Changes**
def format_number(value):
    """Format numbers to show B (billion), M (million), K (thousand) if applicable."""
    try:
        value = float(value)
        if value >= 1_000_000_000:  # Billions
            return f"{value / 1_000_000_000:.3f}B"
        elif value >= 1_000_000:  # Millions
            return f"{value / 1_000_000:.3f}M"
        elif value >= 1_000:  # Thousands
            return f"{value / 1_000:.3f}K"
        else:
            return f"{value:.3f}"  # Show full if below 1K
    except ValueError:
        return str(value)  # Return as is if conversion fails

def convert_to_float(value):
    """Convert string values with 'K', 'M', or 'B' into float numbers."""
    if isinstance(value, str):
        value = value.replace(",", "").strip()  # Remove commas and spaces

        if value.endswith("B"):  # Billions
            return float(value.replace("B", "")) * 1_000_000_000
        elif value.endswith("M"):  # Millions
            return float(value.replace("M", "")) * 1_000_000
        elif value.endswith("K"):  # Thousands
            return float(value.replace("K", "")) * 1_000
        try:
            return float(value)  # Return normal numbers
        except ValueError:
            return 0  # Default to 0 if conversion fails

    return value  # If already a float, return as is

def calculate_changes(new_data, old_data):
    """Calculate daily and monthly asset quantity change, ensuring numeric values."""
    daily_changes = {}
    monthly_changes = {}

    for new in new_data:
        asset_symbol = new["asset_symbol"]
        new_amount = convert_to_float(new["amount"])
        
        # Get the previous day's entry
        old_entry = next((item for item in old_data if item["asset_symbol"] == asset_symbol), None)
        old_amount = convert_to_float(old_entry["amount"]) if old_entry else 0

        # Calculate daily change
        daily_changes[asset_symbol] = new_amount - old_amount if old_entry else "No Data"

        # Calculate monthly change
        total_change = "Shown after 1 month"
        for i in range(1, 31):  # Last 30 days
            past_entry = next((item for item in old_data if item["asset_symbol"] == asset_symbol and item["date"] == (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")), None)
            if past_entry:
                total_change = new_amount - convert_to_float(past_entry["amount"])
                break

        monthly_changes[asset_symbol] = total_change

    return daily_changes, monthly_changes

# **📌 Display Data in Table**
def generate_table():
    """Generate a report table from MySQL data."""
    all_data = load_data_from_mysql()
    if not all_data:
        print("❌ No historical data available.")
        return "❌ No historical data available."

    latest_date = max([entry["date"].strftime("%Y-%m-%d") for entry in all_data])
    new_data = [entry for entry in all_data if entry["date"].strftime("%Y-%m-%d") == latest_date]
    previous_data = [entry for entry in all_data if entry["date"].strftime("%Y-%m-%d") < latest_date]

    if not new_data:
        print("❌ No new data found in database.")
        return "❌ No new data found."

    # Get total_value from the latest data
    total_value = new_data[0]["total_value"] if new_data else "N/A"

    # Convert total_value safely to float
    try:
        total_value = float(total_value.replace("$", "").replace(",", "").strip()) if total_value else 0.0
    except ValueError:
        total_value = 0.0  # Default to 0 if conversion fails

    # Calculate daily & monthly changes
    daily_changes, monthly_changes = calculate_changes(new_data, previous_data)

    table_output = f"🦅 *World Liberty Fi* (Total Portfolio Value: ${total_value:,.2f})\n"

    header = "{:<10} {:<12} {:<12} {:<12}".format("Asset", "Today", "Yesterday", "Last Month")
    table_output += "```\n" + header + "\n" + "-" * 57 + "\n"

    for new in new_data:
        asset_symbol = new["asset_symbol"]
        today_amount = format_number(new["amount"])
        daily_change = format_number(daily_changes.get(asset_symbol, "No Data"))
        monthly_change = format_number(monthly_changes.get(asset_symbol, "Shown after 1 month"))

        table_output += "{:<10} {:<12} {:<12} {:<12}\n".format(
            asset_symbol, today_amount, daily_change, monthly_change
        )

    table_output += "```"
    return table_output


# **📌 Main Execution**
def get_world_liberty():
    msg = generate_table()
    return msg

if __name__ == "__main__":
    # For testing purposes
    print(get_world_liberty())
