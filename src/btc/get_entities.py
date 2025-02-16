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
import docker
from time import sleep
import pandas as pd

# Load environment variables
load_dotenv()

# MySQL Connection Details from .env
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
DB_PORT = int(os.getenv('DB_PORT', 3306))

# Base URL for all entities
BASE_URL = "https://intel.arkm.com/explorer/entity/"

# Entity configurations grouped by category
ENTITIES = {
    "ETFs": {
        "blackrock": {
            "url": f"{BASE_URL}blackrock",
            "table": "blackrock_holdings",
            "title": "BlackRock"
        },
        "fidelity": {
            "url": f"{BASE_URL}fidelity-custody",
            "table": "fidelity_holdings",
            "title": "Fidelity"
        },
        "grayscale": {
            "url": f"{BASE_URL}grayscale",
            "table": "grayscale_holdings",
            "title": "Grayscale"
        },
        "ark": {
            "url": f"{BASE_URL}ark-invest",
            "table": "ark_holdings",
            "title": "ARK Invest"
        },
        "bitwise": {
            "url": f"{BASE_URL}bitwise",
            "table": "bitwise_holdings",
            "title": "Bitwise"
        }
    },
    "CEX": {
        "binance": {
            "url": f"{BASE_URL}binance",
            "table": "binance_holdings",
            "title": "Binance"
        },
        "coinbase": {
            "url": f"{BASE_URL}coinbase",
            "table": "coinbase_holdings",
            "title": "Coinbase"
        },
        "bitfinex": {
            "url": f"{BASE_URL}bitfinex",
            "table": "bitfinex_holdings",
            "title": "Bitfinex"
        },
        "kraken": {
            "url": f"{BASE_URL}kraken",
            "table": "kraken_holdings",
            "title": "Kraken"
        },
        "robinhood": {
            "url": f"{BASE_URL}robinhood",
            "table": "robinhood_holdings",
            "title": "Robinhood"
        }
    },
    "Companies": {
        "microstrategy": {
            "url": f"{BASE_URL}microstrategy",
            "table": "microstrategy_holdings",
            "title": "MicroStrategy"
        },
        "worldliberty": {
            "url": f"{BASE_URL}worldlibertyfi",
            "table": "worldliberty_holdings",
            "title": "World Liberty Fi"
        },
        "usg": {
            "url": f"{BASE_URL}usg",
            "table": "usg_holdings",
            "title": "US Government"
        }
    }
}

# **Rotating User Agents**
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/110.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
]

DEFAULT_ASSETS = {"ETH", "WETH"}

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

def check_and_create_table(cursor, table_name, existing_tables, existing_columns):
    """Check if table exists and create if it doesn't. Return True if table exists/created."""
    try:
        # First check if table exists
        cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
        table_exists = cursor.fetchone() is not None
        
        if not table_exists:
            print(f"Table {table_name} doesn't exist, creating it")
            create_query = f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    date DATE NOT NULL PRIMARY KEY
                )
            """
            cursor.execute(create_query)
        
        # Now get columns regardless of whether table was just created or existed
        cursor.execute(f"SHOW COLUMNS FROM {table_name}")
        columns = {row['Field'] for row in cursor.fetchall()}
        existing_tables.append(table_name)
        existing_columns.update(columns)
        print(f"Found table {table_name}")
        return True
    except Exception as e:
        print(f"Error checking/creating table {table_name}: {e}")
        return False

def get_table_info(cursor, entity_config):
    """Get all tables and their columns for an entity. Returns (existing_tables, table_columns)."""
    existing_tables = []
    table_columns = {}
    
    # Check numbered tables
    table_num = 1
    while True:
        table_name = f"{entity_config['table']}{table_num}"
        try:
            cursor.execute(f"SHOW COLUMNS FROM {table_name}")
            columns = {row['Field'] for row in cursor.fetchall()}
            if 'date' in columns:
                columns.remove('date')
            existing_tables.append(table_name)
            table_columns[table_name] = columns
            table_num += 1
        except Exception:
            break
            
    return existing_tables, table_columns

def create_tables_if_not_exist(entity_config, html_content=None):
    """Create tables for entity if they don't exist."""
    print(f"\nChecking tables for {entity_config['title']}")
    
    # Fetch data if not provided
    if not html_content:
        html_content = fetch_data_with_firefox(entity_config['url'])
        if not html_content:
            print("Unable to fetch data from website")
            return None
        print("Successfully fetched HTML content")
    
    connection = connect_to_database()
    if not connection:
        return None

    try:
        with connection.cursor() as cursor:
            # Get crypto list from HTML
            soup = BeautifulSoup(html_content, "html.parser")
            holdings_containers = soup.find_all("div", class_="Portfolio_holdingsContainer__XyaUq")
            crypto_list = []
            
            for container in holdings_containers:
                symbol_span = container.find("span", class_="Portfolio_holdingsSymbol__uOpkQ")
                if symbol_span:
                    symbol = symbol_span.get_text(strip=True)
                    if symbol not in crypto_list:
                        crypto_list.append(symbol)

            print(f"Found {len(crypto_list)} unique cryptocurrencies")
            
            # Get existing tables and columns
            existing_tables, table_columns = get_table_info(cursor, entity_config)
            
            # Get all existing cryptos across all tables
            all_existing_cryptos = set()
            for columns in table_columns.values():
                all_existing_cryptos.update(columns)
            
            # Find new cryptocurrencies
            new_cryptos = [crypto for crypto in crypto_list if crypto not in all_existing_cryptos]
            
            if new_cryptos:
                print(f"Found {len(new_cryptos)} new cryptocurrencies to add")
                
                if not existing_tables:
                    # Calculate how many tables we need for new cryptos
                    num_tables_needed = (len(new_cryptos) // 500) + (1 if len(new_cryptos) % 500 > 0 else 0)
                    print(f"Creating {num_tables_needed} new tables")
                    
                    # Create all needed tables
                    for table_num in range(num_tables_needed):
                        start_idx = table_num * 500
                        end_idx = min((table_num + 1) * 500, len(new_cryptos))
                        table_cryptos = new_cryptos[start_idx:end_idx]
                        
                        table_name = f"{entity_config['table']}{table_num + 1}"
                        create_query = f"""
                            CREATE TABLE IF NOT EXISTS {table_name} (
                                date DATE NOT NULL PRIMARY KEY,
                                {', '.join(f'`{symbol}` DECIMAL(32,4)' for symbol in table_cryptos)}
                            )
                        """
                        cursor.execute(create_query)
                        connection.commit()
                        print(f"Created {table_name} with {len(table_cryptos)} columns")
                        
                        existing_tables.append(table_name)
                        table_columns[table_name] = set(table_cryptos)
                else:
                    # Add to existing tables logic (unchanged)
                    last_table = existing_tables[-1]
                    last_table_columns = len(table_columns[last_table])
                    
                    for symbol in new_cryptos:
                        if last_table_columns >= 500:
                            new_table = f"{entity_config['table']}{len(existing_tables) + 1}"
                            create_query = f"""
                                CREATE TABLE IF NOT EXISTS {new_table} (
                                    date DATE NOT NULL PRIMARY KEY
                                )
                            """
                            cursor.execute(create_query)
                            connection.commit()
                            existing_tables.append(new_table)
                            table_columns[new_table] = set()
                            last_table = new_table
                            last_table_columns = 0
                        
                        try:
                            cursor.execute(f"""
                                ALTER TABLE {last_table}
                                ADD COLUMN `{symbol}` DECIMAL(32,4)
                            """)
                            connection.commit()
                            print(f"Added column {symbol} to {last_table}")
                            last_table_columns += 1
                            table_columns[last_table].add(symbol)
                        except Exception as e:
                            if "Duplicate column" not in str(e):
                                print(f"Error adding column {symbol} to {last_table}: {e}")
            else:
                print("No new cryptocurrencies to add")
            
            return html_content, existing_tables, table_columns
            
    except Exception as e:
        print(f"Error managing tables: {e}")
        return None
    finally:
        connection.close()

# **📌 Fetch Data with Selenium**
def fetch_data_with_firefox(url):
    """Fetch data using Selenium in Docker container."""
    container_name = "selenium-firefox"
    image_name = "selenium/standalone-firefox"
    max_retries = 10
    success = False
    retries = 0
    driver = None

    try:
        # Clean up any existing container first
        client = docker.from_env()
        try:
            container = client.containers.get(container_name)
            print(f"Found existing container {container_name}, removing it...")
            container.stop()
            container.remove()
        except docker.errors.NotFound:
            print(f"No existing container {container_name} found")

        # Start Docker container
        print(f"Starting new {container_name} container...")
        client.containers.run(
            image_name,
            name=container_name,
            ports={"4444/tcp": 4444},
            detach=True,
        )
        print("Docker container started")

        while not success and retries < max_retries:
            try:
                options = webdriver.FirefoxOptions()
                options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
                options.add_argument("--headless")
                
                driver = webdriver.Remote(
                    command_executor="http://localhost:4444/wd/hub",
                    options=options
                )
                success = True
            except Exception as e:
                print(f"Error initializing WebDriver: {e}")
                retries += 1
                sleep_time = random.randint(1, 10)
                print(f"Attempt {retries}/{max_retries}")
                time.sleep(sleep_time)

        if not success:
            return None

        print("Launching Firefox Browser...")
        driver.get(url)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CLASS_NAME, "Portfolio_holdingsContainer__XyaUq"))
        )
        time.sleep(5)

        print("Page Loaded. Extracting content...")
        return driver.page_source

    except Exception as e:
        print(f"Firefox Error: {e}")
        return None
    finally:
        if driver:
            driver.quit()

# **📌 Extract Data**
def extract_holdings_and_value(html_content):
    """Extract holdings from HTML content."""
    if not html_content:
        print("No HTML content to parse")
        return None

    soup = BeautifulSoup(html_content, "html.parser")
    holdings_data = {}
    processed_symbols = set()

    # Find all holdings containers
    holdings_containers = soup.find_all("div", class_="Portfolio_holdingsContainer__XyaUq")
    print(f"Found {len(holdings_containers)} holdings containers")

    for container in holdings_containers:
        try:
            # Get symbol first
            symbol_span = container.find("span", class_="Portfolio_holdingsSymbol__uOpkQ")
            if not symbol_span:
                continue
            symbol = symbol_span.get_text(strip=True)

            # Skip if we've already processed this symbol
            if symbol in processed_symbols:
                continue

            # Get amount (first span in container)
            amount_span = container.find("span")
            if not amount_span:
                continue
            amount_text = amount_span.get_text(strip=True)

            # Convert B/M/K/T values to full numbers
            try:
                if amount_text.endswith('T'):
                    amount = float(amount_text[:-1]) * 1_000_000_000_000
                elif amount_text.endswith('B'):
                    amount = float(amount_text[:-1]) * 1_000_000_000
                elif amount_text.endswith('M'):
                    amount = float(amount_text[:-1]) * 1_000_000
                elif amount_text.endswith('K'):
                    amount = float(amount_text[:-1]) * 1_000
                else:
                    amount = float(amount_text.replace(",", ""))

                # Validate the converted amount
                if not isinstance(amount, (int, float)):
                    print(f"Invalid amount type for {symbol}: {type(amount)}")
                    continue
                if amount < 0:
                    print(f"Negative amount for {symbol}: {amount}")
                    continue

                holdings_data[symbol] = amount
                processed_symbols.add(symbol)

            except ValueError as e:
                print(f"Error converting amount for {symbol}: {amount_text} - {str(e)}")
                continue
            except Exception as e:
                print(f"Error processing {symbol}: {str(e)}")
                continue

        except Exception as e:
            print(f"Error processing container: {str(e)}")
            continue

    if not holdings_data:
        print("No valid holdings data extracted")
        return None

    print(f"Successfully extracted {len(holdings_data)} holdings")
    return holdings_data

# **📌 Save Data to MySQL**
def save_data_to_mysql(entity_config, holdings_data, existing_tables=None, table_columns=None):
    """Save data using appropriate table structure."""
    if not holdings_data:
        print("No holdings data to save")
        return

    connection = connect_to_database()
    if not connection:
        return

    today_date = datetime.now().strftime("%Y-%m-%d")
    print(f"Saving data for date: {today_date}")
    
    try:
        with connection.cursor() as cursor:
            # Get table info if not provided
            if not existing_tables or not table_columns:
                existing_tables, table_columns = get_table_info(cursor, entity_config)

            # Save data to appropriate tables
            for table_name in existing_tables:
                # Filter holdings data for this table's columns
                table_holdings = {k: v for k, v in holdings_data.items() 
                                if k in table_columns[table_name]}
                
                if table_holdings:
                    # Prepare column names and values
                    columns = ["date"] + list(table_holdings.keys())
                    values = [today_date] + list(table_holdings.values())
                    
                    # Create placeholders and update string
                    placeholders = ", ".join(["%s"] * len(columns))
                    columns_str = ", ".join(f"`{col}`" for col in columns)
                    update_str = ", ".join(
                        f"`{col}` = VALUES(`{col}`)" 
                        for col in columns 
                        if col != "date"
                    )

                    query = f"""
                        INSERT INTO {table_name} ({columns_str})
                        VALUES ({placeholders})
                        ON DUPLICATE KEY UPDATE {update_str}
                    """
                    
                    cursor.execute(query, values)
                    connection.commit()
                    print(f"Successfully saved data to {table_name}")
    
    except Exception as e:
        print(f"MySQL Save Error: {e}")
        connection.rollback()
    finally:
        connection.close()

# **📌 Load Data for Comparison**
def load_data_from_mysql(entity_config):
    """Load data from all tables for an entity."""
    connection = connect_to_database()
    if not connection:
        return []

    try:
        with connection.cursor() as cursor:
            all_data = []
            existing_tables = []
            
            # First check base table
            try:
                cursor.execute(f"SHOW TABLES LIKE '{entity_config['table']}'")
                if cursor.fetchone():
                    existing_tables.append(entity_config['table'])
            except Exception:
                pass
                
            # Then check numbered tables
            table_num = 1
            while True:
                table_name = f"{entity_config['table']}{table_num}"
                try:
                    cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
                    if cursor.fetchone():
                        existing_tables.append(table_name)
                        table_num += 1
                    else:
                        break
                except Exception:
                    break
            
            if not existing_tables:
                return []
            
            # Load and merge data from all tables
            for i, table_name in enumerate(existing_tables):
                cursor.execute(f"SELECT * FROM {table_name} ORDER BY date DESC")
                table_data = cursor.fetchall()
                
                if i == 0:
                    all_data = table_data  # First table data becomes base
                else:
                    # Merge additional table data
                    for j, row in enumerate(all_data):
                        if j < len(table_data):
                            all_data[j].update({k: v for k, v in table_data[j].items() 
                                              if k not in ['date']})
            
            return all_data
    finally:
        connection.close()

# **📌 Calculate Changes**
def format_number(value):
    """Format number to show minimal necessary decimals."""
    value = float(value)
    if value == 0:
        return "0"
    
    # Convert to string with max precision
    str_value = f"{value:.8f}".rstrip('0').rstrip('.')
    
    # If it's a whole number, format with commas
    if '.' not in str_value:
        return f"{int(value):,}"
    
    return f"{float(str_value):,}"

def convert_to_float(value):
    """Convert string values with 'K', 'M', or 'B' into float numbers."""
    if isinstance(value, str):
        value = value.replace(",", "").strip()

        if value.endswith("B"):  # Billions
            return float(value.replace("B", "")) * 1_000_000_000
        elif value.endswith("M"):  # Millions
            return float(value.replace("M", "")) * 1_000_000
        elif value.endswith("K"):  # Thousands
            return float(value.replace("K", "")) * 1_000
        try:
            return float(value)
        except ValueError:
            return 0

    return value

def calculate_changes(new_data, old_data):
    """Calculate daily and monthly asset quantity change, ensuring numeric values."""
    daily_changes = {}
    monthly_changes = {}

    for new in new_data:
        asset_symbol = new["asset_symbol"]
        new_amount = convert_to_float(new["amount"])
        
        # ✅ Get the previous day's entry
        old_entry = next((item for item in old_data if item["asset_symbol"] == asset_symbol), None)
        old_amount = convert_to_float(old_entry["amount"]) if old_entry else 0

        # ✅ Calculate daily change
        daily_changes[asset_symbol] = new_amount - old_amount if old_entry else "No Data"

        # ✅ Calculate monthly change
        total_change = "Shown after 1 month"
        for i in range(1, 31):  # Last 30 days
            past_entry = next((item for item in old_data 
                             if item["asset_symbol"] == asset_symbol 
                             and item["date"] == (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")), None)
            if past_entry:
                total_change = new_amount - convert_to_float(past_entry["amount"])
                break

        monthly_changes[asset_symbol] = total_change

    return daily_changes, monthly_changes


def get_streaks(df, columns):
    """Find the longest buying/selling streaks."""
    if len(df) < 2:  # Need at least today and yesterday
        return [], []
        
    streaks = {}
    for column in columns:
        if column not in df.columns:
            continue
            
        # Convert column to float type before diff
        df[column] = df[column].astype(float)
        changes = df[column].diff().iloc[1:]  # Skip first NaN from diff()
        
        direction = None
        streak_count = 0
        for change in changes[::-1]:
            if pd.isna(change):  # Skip NaN values
                continue
                
            if change > 0:
                if direction == "buying" or direction is None:
                    direction = "buying"
                    streak_count += 1
                else:
                    break
            elif change < 0:
                if direction == "selling" or direction is None:
                    direction = "selling"
                    streak_count += 1
                else:
                    break
            else:
                break
                
        if streak_count > 1: 
            streaks[column] = (direction, streak_count)

    if not streaks:
        return [], []
        
    # Group assets by direction and streak count
    max_streak = max(streak[1] for streak in streaks.values())
    buying_assets = [asset for asset, (dir, count) in streaks.items() 
                    if count == max_streak and dir == "buying"]
    selling_assets = [asset for asset, (dir, count) in streaks.items() 
                     if count == max_streak and dir == "selling"]
    
    # Create simplified messages
    messages = []
    for asset in buying_assets:
        messages.append(f"{asset} buying for *{max_streak} days straight*")
    for asset in selling_assets:
        messages.append(f"{asset} selling for *{max_streak} days straight*")
    
    return buying_assets + selling_assets, messages

def get_reversal(df, columns):
    """Find buying to selling and selling to buying reversals."""
    if len(df) < 3:  # Need at least 3 days to detect reversal
        return [], []
        
    assets = []
    messages = []
    for column in columns:
        if column not in df.columns:
            continue
        changes = df[column].diff().iloc[1:]
        today_change = changes.iloc[-1]
        
        # Count the streak before the reversal
        streak_count = 0
        prev_direction = None
        for change in changes.iloc[::-1]:
            if change == 0:
                break
            if prev_direction is None:
                prev_direction = "selling" if change < 0 else "buying"
                streak_count = 1
            elif (change < 0 and prev_direction == "selling") or (change > 0 and prev_direction == "buying"):
                streak_count += 1
            else:
                break
                
        # Check if today reversed the streak
        if streak_count >= 1:
            if (today_change > 0 and prev_direction == "selling") or (today_change < 0 and prev_direction == "buying"):
                direction = "buying" if today_change > 0 else "selling"
                
                assets.append(column)
                messages.append(
                    f"Position in {column} shifted to {direction} after {prev_direction} streak of {streak_count} days"
                )
    
    return assets, messages

def get_max_changes(df, columns):
    """Find maximum percentage increases and decreases."""
    if len(df) < 2:  # Need at least today and yesterday
        return [], []
        
    assets = []
    messages = []
    max_increase = (None, -float('inf'))
    max_decrease = (None, float('inf'))
    
    for column in columns:
        if column not in df.columns:
            continue
            
        today_value = df[column].iloc[-1]
        yesterday_value = df[column].iloc[-2]
        
        if yesterday_value == 0:
            continue
            
        pct_change = ((today_value - yesterday_value) / yesterday_value) * 100
        
        if pct_change > max_increase[1]:
            max_increase = (column, pct_change)
        if pct_change < max_decrease[1]:
            max_decrease = (column, pct_change)
    
    if max_increase[0] and max_increase[1] > 0:
        assets.append(max_increase[0])
        # Calculate absolute change
        today_value = df[max_increase[0]].iloc[-1]
        yesterday_value = df[max_increase[0]].iloc[-2]
        abs_change = int(today_value - yesterday_value)
        messages.append(
            f"{max_increase[0]} +{format(abs_change, ',')} (*{max_increase[1]:+.2f}%*)"
        )
        
    if max_decrease[0] and max_decrease[1] < 0:
        assets.append(max_decrease[0])
        # Calculate absolute change
        today_value = df[max_decrease[0]].iloc[-1]
        yesterday_value = df[max_decrease[0]].iloc[-2]
        abs_change = int(today_value - yesterday_value)
        messages.append(
            f"{max_decrease[0]} {format(abs_change, ',')} (*{max_decrease[1]:+.2f}%*)"
        )
    
    return assets, messages

def get_insight(df, display_columns=None):
    """Generate insights from the data."""
    insights = []
    display_assets = set()
    
    # Use all columns except 'date', USDT and USDC if no display_columns provided
    if display_columns is None:
        display_columns = [col for col in df.columns if col != 'date' and 'USDT' not in col and 'USDC' not in col]
    
    # Get all insights but keep them separate
    streak_assets, streak_msgs = get_streaks(df, display_columns)
    reversal_assets, reversal_msgs = get_reversal(df, display_columns)
    change_assets, change_msgs = get_max_changes(df, display_columns)
    
    # Add messages in specific order:
    # 1. Changes (increases/decreases)
    # 2. Streaks
    # 3. Reversals
    insights.extend(change_msgs)
    insights.extend(streak_msgs)
    insights.extend(reversal_msgs)
    
    # Collect unique assets for display
    display_assets.update(change_assets)
    display_assets.update(streak_assets)
    display_assets.update(reversal_assets)
    
    if not insights:
        return None, list(display_assets)
    
    return insights, list(display_assets)

def check_column_overlaps(cursor, entity_config):
    """Debug function to check for any column overlaps between tables."""
    print(f"\nChecking for column overlaps in {entity_config['title']} tables...")
    
    # Get all tables for this entity
    table_num = 1
    tables = []
    columns_by_table = {}
    
    while True:
        table_name = f"{entity_config['table']}{table_num}"
        try:
            cursor.execute(f"SHOW COLUMNS FROM {table_name}")
            columns = {row['Field'] for row in cursor.fetchall()}
            if 'date' in columns:
                columns.remove('date')
            tables.append(table_name)
            columns_by_table[table_name] = columns
            table_num += 1
        except Exception:
            break
    
    if not tables:
        print("No tables found")
        return False
    
    # Check for overlaps
    overlaps_found = False
    for i, table1 in enumerate(tables):
        for table2 in tables[i+1:]:
            overlap = columns_by_table[table1] & columns_by_table[table2]
            if overlap:
                overlaps_found = True
                print(f"⚠️ Found overlapping columns between {table1} and {table2}:")
                print(f"  Overlapping columns: {sorted(overlap)}")
    
    # Check column counts
    for table in tables:
        column_count = len(columns_by_table[table])
        if column_count > 500:
            overlaps_found = True
            print(f"⚠️ Table {table} has {column_count} columns (exceeds 500 limit)")
    
    # Print summary
    total_unique_columns = len(set().union(*columns_by_table.values()))
    print(f"\nSummary for {entity_config['title']}:")
    print(f"- Found {len(tables)} tables")
    print(f"- Total unique columns across all tables: {total_unique_columns}")
    for table in tables:
        print(f"- {table}: {len(columns_by_table[table])} columns")
    
    if not overlaps_found:
        print("✅ No overlaps or issues found")
    
    return not overlaps_found

# **📌 Main Execution**
def get_entity_data(entity_config):
    """Main function to fetch and process entity data."""
    print(f"\n=== Starting {entity_config['title']} Data Collection ===")
    
    connection = connect_to_database()
    if not connection:
        return None
        
    try:
        with connection.cursor() as cursor:
            today_date = datetime.now().strftime("%Y-%m-%d")
            
            # Get table info once
            existing_tables, table_columns = get_table_info(cursor, entity_config)
            
            if not existing_tables:
                print("No tables found, will create new ones")
                html_content = fetch_data_with_firefox(entity_config['url'])
                if not html_content:
                    return None
                result = create_tables_if_not_exist(entity_config, html_content)
                if not result:
                    return None
                html_content, existing_tables, table_columns = result
                
                # Process and save new data
                holdings_data = extract_holdings_and_value(html_content)
                if not holdings_data:
                    print("Unable to extract holdings data")
                    return None
                
                save_data_to_mysql(entity_config, holdings_data, 
                                 existing_tables, table_columns)
            else:
                # Check if today's data exists in any table
                has_today_data = False
                for table_name in existing_tables:
                    cursor.execute(f"""
                        SELECT COUNT(*) as count 
                        FROM {table_name} 
                        WHERE date = %s
                    """, (today_date,))
                    result = cursor.fetchone()
                    if result and result['count'] > 0:
                        has_today_data = True
                        print(f"Found today's data in {table_name}")
                        break
                
                if not has_today_data:
                    print("No data for today, fetching new data")
                    html_content = fetch_data_with_firefox(entity_config['url'])
                    if not html_content:
                        return None
                    
                    holdings_data = extract_holdings_and_value(html_content)
                    if not holdings_data:
                        print("Unable to extract holdings data")
                        return None
                    
                    save_data_to_mysql(entity_config, holdings_data, 
                                     existing_tables, table_columns)
                else:
                    print("Today's data already exists")
            
            return load_data_from_mysql(entity_config)
            
    except Exception as e:
        print(f"Error in get_entity_data: {e}")
        return None
    finally:
        connection.close()

def format_insights_message(all_insights):
    """Format insights into a readable message."""
    message = "🐋 *WHALE TRACKER (holding changes)*\n\n"
    no_changes_by_category = {}
    
    for category, entities in ENTITIES.items():
        has_insights = False
        category_message = f"*{category}*\n"
        temp_message = ""
        category_no_changes = []
        
        for entity_name, entity_config in entities.items():
            if category not in all_insights or entity_name not in all_insights[category]:
                category_no_changes.append(entity_config['title'])
            else:
                has_insights = True
                changes = all_insights[category][entity_name]
                temp_message += f"│   {entity_config['title']}\n"
                for change in changes:
                    temp_message += f"│   └── {change}\n"
        
        if has_insights:
            message += category_message + temp_message
            if category != list(ENTITIES.keys())[-1]:
                message += "\n"

        if category_no_changes:
            no_changes_by_category[category] = category_no_changes
    
    if no_changes_by_category:
        message += "\n*Entities with No Portfolio Changes*\n"
        for category, entities in no_changes_by_category.items():
            message += f"│   {category}: {', '.join(entities)}\n"
    
    return message

def get_entities():
    """Main function to process all entities and generate insights."""
    all_insights = {}
    
    try:
        # Start Docker container at beginning
        client = docker.from_env()
        container_name = "selenium-firefox"
        
        # Clean up any existing container first
        try:
            container = client.containers.get(container_name)
            print(f"Found existing container {container_name}, removing it...")
            container.stop()
            container.remove()
        except docker.errors.NotFound:
            print(f"No existing container {container_name} found")

        # Start new container
        print(f"Starting new {container_name} container...")
        client.containers.run(
            "selenium/standalone-firefox",
            name=container_name,
            ports={"4444/tcp": 4444},
            detach=True,
        )
        print("Docker container started")
        
        connection = connect_to_database()
        if not connection:
            return "Error connecting to database"
            
        try:
            with connection.cursor() as cursor:
                # First check for any overlaps
                for category, entities in ENTITIES.items():
                    for entity_name, entity_config in entities.items():
                        check_column_overlaps(cursor, entity_config)
        finally:
            connection.close()
        
        # Process all entities
        for category, entities in ENTITIES.items():
            category_insights = {}
            for entity_name, entity_config in entities.items():
                print(f"\nProcessing {entity_config['title']}...")
                
                entity_data = get_entity_data(entity_config)
                if entity_data and len(entity_data) > 0:
                    try:
                        df = pd.DataFrame(list(entity_data))
                        if not df.empty:
                            df['date'] = pd.to_datetime(df['date'])
                            df = df.sort_values('date', ascending=True)
                            insights, _ = get_insight(df)
                            if insights:
                                category_insights[entity_name] = insights
                    except Exception as e:
                        print(f"Error processing data for {entity_config['title']}: {e}")
                else:
                    print(f"No data available for {entity_config['title']}")
            
            if category_insights:
                all_insights[category] = category_insights
        
        # Format and return the final message
        if all_insights:
            return format_insights_message(all_insights)
        else:
            return "No insights generated for any entity"
        
    except Exception as e:
        print(f"\nError in main process: {e}")
        return f"Error processing entities: {str(e)}"
    finally:
        # Clean up Docker container at the end
        try:
            container = client.containers.get(container_name)
            print(f"\nStopping and removing {container_name} container...")
            container.stop()
            container.remove()
            print("Container cleanup completed")
        except docker.errors.NotFound:
            print(f"Container {container_name} already removed")
        except Exception as e:
            print(f"Error cleaning up container: {e}")

if __name__ == "__main__":
    msg = get_entities()

    if msg:
        print("\nFinal message:")
        print(msg)
    else:
        print("\nNo insights generated")
        