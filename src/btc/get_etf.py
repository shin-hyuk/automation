import docker
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from collections import defaultdict
import random
import time
import platform
import os
import holidays

# Define US public holidays (or adjust for your region)
us_holidays = holidays.US()

# Docker container settings
CONTAINER_NAME = "selenium-firefox"
IMAGE_NAME = "selenium/standalone-firefox"
SELENIUM_REMOTE_URL = "http://localhost:4444/wd/hub"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/110.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
]

URL = "https://farside.co.uk/bitcoin-etf-flow-all-data"


def get_docker_client():
    system = platform.system()
    
    # Set the Docker environment variable based on the OS
    if system == "Windows":
        os.environ["DOCKER_HOST"] = "npipe:////./pipe/docker_engine"  # Docker Desktop on Windows
    elif system == "Linux":
        os.environ["DOCKER_HOST"] = "unix:///var/run/docker.sock"  # Native Docker Engine on Linux
    # For Mac, Docker Desktop uses the default setup, no changes needed.
    
    return docker.from_env()  # Return Docker client

def start_docker_container():
    client = get_docker_client()
    try:
        container = client.containers.get(CONTAINER_NAME)
        if container.status != "running":
            container.start()
        print(f"Container {CONTAINER_NAME} is running.")
    except docker.errors.NotFound:
        print(f"Container {CONTAINER_NAME} not found. Creating and starting it.")
        client.containers.run(
            IMAGE_NAME,
            name=CONTAINER_NAME,
            ports={"4444/tcp": 4444},
            detach=True,
        )

def stop_docker_container():
    client = get_docker_client()
    try:
        container = client.containers.get(CONTAINER_NAME)
        print(f"Stopping container: {CONTAINER_NAME}")
        container.stop()
    except docker.errors.NotFound:
        print(f"Container {CONTAINER_NAME} not found. Skipping stop.")

def fetch_data_with_selenium():
    driver = None
    max_retries = 10
    success = False
    retries = 0
    
    while not success and retries < max_retries:
        try:
            options = webdriver.FirefoxOptions()
            options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
            options.add_argument("--no-sandbox")
            options.add_argument("--headless")
            
            driver = webdriver.Remote(
                command_executor=SELENIUM_REMOTE_URL,
                options=options
            )
            success = True  # If no exception, the driver is successfully created
        except Exception as e:
            print(f"Error initializing WebDriver: {type(e).__name__}: {e}")
            retries += 1
            sleep_time = random.randint(1, 10)
            print(f"Attempt {retries}/{max_retries} failed: {e}")
            print(f"Retrying in {sleep_time} seconds...")
            time.sleep(sleep_time)
    
    try:
        print("Navigating to the URL...")
        driver.get(URL)
        print("Page loaded, waiting for elements...")

        WebDriverWait(driver, 120).until(
            EC.presence_of_element_located((By.CLASS_NAME, "etf"))
        )
        
        print("Fetching page content...")
        content = driver.page_source
        return content
    except Exception as e:
        print(f"Error fetching the page: {e}")
        return None
    finally:
        if driver:
            driver.quit()

# Other functions remain unchanged (extracting table data, parsing, processing, filtering, etc.)

def extract_table_data(html_content):
    """Extract the table data from the HTML content."""
    if not html_content:
        print("No HTML content to parse.")
        return [], []

    soup = BeautifulSoup(html_content, "html.parser")

    # Locate the table
    table = soup.find("table", {"class": "etf"})
    if not table:
        print("No table found in the HTML.")
        return [], []

    print("Table found! Extracting data...")

    # Extract column titles from <thead>
    column_titles = []
    thead = table.find("thead")
    if thead:
        column_titles = [th.get_text(strip=True) for th in thead.find_all("th")]
    else:
        print("No <thead> found. Using default column titles.")
        column_titles = ["Column 1", "Column 2", "Column 3", "Column 4"]

    # Extract rows from <tbody>
    tbody = table.find("tbody")
    extracted_data = []
    if tbody:
        rows = tbody.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            row_data = [col.get_text(strip=True) for col in cols]
            if row_data:
                extracted_data.append(row_data)
    else:
        print("No <tbody> found.")

    return column_titles, extracted_data

def parse_value(value):
    """Convert a value to float, handling parentheses as negative and commas in numbers."""
    if isinstance(value, str):
        if value == "-":
            return None
        value = value.replace(",", "")  # Remove commas
        if value.startswith("(") and value.endswith(")"):
            return -float(value.strip("()"))
        return float(value)
    return value  # Return the value as is if it's already a float

def process_table_data(data):
    """Process table rows by handling negative and missing values."""
    processed_data = []
    for row in data:
        processed_row = [parse_value(col) if i > 0 else col for i, col in enumerate(row)]
        processed_data.append(processed_row)
    return processed_data

def filter_latest_two_months(data):
    """Filter rows to include only the latest two months."""
    filtered_data = []
    today = datetime.now()
    two_months_ago = today - timedelta(days=90)

    for row in data:
        try:
            row_date = datetime.strptime(row[0], "%d %b %Y")  # Format: '23 Jan 2025'
            if row_date >= two_months_ago:
                filtered_data.append(row)
        except ValueError:
            print(f"Skipping invalid date format: {row[0]}")

    return filtered_data

import holidays

# Define US holidays (Adjust for your region if necessary)
us_holidays = holidays.US()

def calculate_changes(data, column_index):
    """Retrieve latest, previous trading day's values, ensuring Monday compares to Friday."""
    changes = {
        "latest_value": "No Data",  
        "previous_trading_value": "No Data",  
        "monthly_change": None,  
    }

    # Sort data by date (descending order)
    sorted_data = sorted(data, key=lambda row: datetime.strptime(row[0], "%d %b %Y"), reverse=True)

    today_date = datetime.now().date()
    latest_value = None
    previous_trading_value = None

    # If today is a weekend or holiday, keep "No Data"
    if today_date.weekday() in [5, 6] or today_date in us_holidays:
        pass  

    else:
        # If today is a trading day, get its value
        for row in sorted_data:
            row_date = datetime.strptime(row[0], "%d %b %Y").date()
            if row_date == today_date:
                latest_value = row[column_index]
                break

    # Find the previous trading day
    previous_trading_date = today_date - timedelta(days=1)

    # If today is Monday, go back to **Friday**
    if today_date.weekday() == 0:  # Monday
        previous_trading_date -= timedelta(days=2)

    # Ensure we correctly find Friday’s data
    while previous_trading_date.weekday() in [5, 6] or previous_trading_date in us_holidays:
        previous_trading_date -= timedelta(days=1)

    # Get the previous trading day's value
    for row in sorted_data:
        row_date = datetime.strptime(row[0], "%d %b %Y").date()
        if row_date == previous_trading_date:
            previous_trading_value = row[column_index]
            break

    # Ensure correct assignment
    changes["latest_value"] = latest_value if latest_value is not None else "No Data"
    changes["previous_trading_value"] = previous_trading_value if previous_trading_value is not None else "No Data"

    # Last Month Calculation - Ensure we remove None values
    start_of_last_30_days = today_date - timedelta(days=30)
    monthly_values = [row[column_index] for row in sorted_data if datetime.strptime(row[0], "%d %b %Y").date() >= start_of_last_30_days]

    # **Filter out None values before summing**
    valid_monthly_values = [v for v in monthly_values if v is not None]

    changes["monthly_change"] = sum(valid_monthly_values) if valid_monthly_values else "N/A"

    return changes

def create_changes_table(column_titles, data):
    """Create a changes table for IBIT, FBTC, and BITB."""
    assets = {"BlackRock (IBIT)": 1, "Fidelity (FBTC)": 2, "Bitwise (BITB)": 3}  # Column indexes for each asset
    changes_table = defaultdict(dict)

    for asset, col_index in assets.items():
        changes_table[asset] = calculate_changes(data, col_index)

    return changes_table

def display_changes_table(changes_table, sorted_data):
    """Display the changes table using latest and previous trading day values."""
    msg = ""
    latest_date = sorted_data[0][0] if sorted_data else "No Data"
    msg += f"📊 *ETFs/ETPs* (As of {latest_date})\n"
    msg += "```\n"
    msg += f"{'Asset':<20}  {'Today':<15}  {'Previous Trading Day':<25}  {'Last Month':<15}\n"
    msg += "-" * 76 + "\n"

    for asset, changes in changes_table.items():
        latest = f"{changes['latest_value']:.2f}M" if isinstance(changes['latest_value'], (int, float)) else changes['latest_value']
        prev_trading = f"{changes['previous_trading_value']:.2f}M" if isinstance(changes['previous_trading_value'], (int, float)) else changes['previous_trading_value']
        monthly = f"{changes['monthly_change']:.2f}M" if isinstance(changes['monthly_change'], (int, float)) else "N/A"

        msg += f"{asset:<20}  {latest:<15}  {prev_trading:<25}  {monthly:<15}\n"

    msg += "```"
    return msg


def calculate_average_last_30_days(data, column_index):
    """Calculate the average of a specific column in the data for the last 30 days."""
    today = datetime.now()  # Use the current date
    thirty_days_ago = today - timedelta(days=30)
    
    # Filter data for the last 30 days
    recent_data = [row for row in data if row[0] is not None and datetime.strptime(row[0], "%d %b %Y") >= thirty_days_ago]
    
    # Calculate the average
    values = [row[column_index] for row in recent_data if row[column_index] is not None]
    return sum(values) / len(values) if values else 0


def detect_sudden_buys(data, column_index, threshold=1.5):
    """Detect sudden buys that are higher than the average by a threshold factor."""
    average = calculate_average_last_30_days(data, column_index)
    sudden_buys = [row for row in data if row[column_index] is not None and row[column_index] > average * threshold]
    return sudden_buys

def detect_sudden_buys_today(data, column_index, today_date, threshold=1.5):
    """Detect sudden buys for today's data that are higher than the average by a threshold factor."""
    average = calculate_average_last_30_days(data, column_index)
    sudden_buys = [row for row in data if row[column_index] is not None and row[column_index] > average * threshold and datetime.strptime(row[0], "%d %b %Y") == today_date]
    return sudden_buys

def detect_continuous_trend(data, column_index, trend='buy', days=3):
    """Detect continuous buying or selling over a specified number of days."""
    sorted_data = sorted(data, key=lambda row: datetime.strptime(row[0], "%d %b %Y"), reverse=True)
    count = 0
    for row in sorted_data:
        value = row[column_index]
        if value is None:
            continue
        if (trend == 'buy' and value > 0) or (trend == 'sell' and value < 0):
            count += 1
            if count >= days:
                return True
        else:
            count = 0
    return False

def get_etf():
    start_docker_container()
    html_content = fetch_data_with_selenium()

    # Parse the HTML content
    column_titles, data = extract_table_data(html_content)

    # Parse the data
    parsed_data = [[row[0]] + [parse_value(val) for val in row[1:]] for row in data]

    # Filter out summary rows (Total, Average, Maximum, Minimum)
    filtered_parsed_data = [row for row in parsed_data if row[0] not in ['Total', 'Average', 'Maximum', 'Minimum']]

    # Filter the data to include only the latest two months
    filtered_data = filter_latest_two_months(filtered_parsed_data)

    # Process the table data
    processed_data = process_table_data(filtered_data)

    # Calculate changes for IBIT, FBTC, and BITB
    changes_table = create_changes_table(column_titles, processed_data)

    # Sort the data to get the latest date dynamically
    sorted_data = sorted(processed_data, key=lambda row: datetime.strptime(row[0], "%d %b %Y"), reverse=True)

    # Detect sudden buys for today's data for IBIT, FBTC, and BITB
    today_date = datetime.now().date()
    analysis_msg = ""
    message_count = 1
    assets = {"BlackRock (IBIT)": 1, "Fidelity (FBTC)": 2, "Bitwise (BITB)": 3}  # Column indexes for each asset
    for asset, col_index in assets.items():
        sudden_buys_today = detect_sudden_buys_today(processed_data, col_index, today_date)
        if sudden_buys_today:
            analysis_msg += f"{message_count}) Sudden buys detected today for {asset}: {sudden_buys_today}\n"
            message_count += 1

    # If no sudden buys were detected, add a message indicating no changes
    if not analysis_msg:
        analysis_msg = f"*{message_count}*) No sudden changes detected today."
        message_count += 1

    # Detect continuous buying or selling for 3 days for IBIT, FBTC, and BITB
    trend_analysis_msg = ""
    for asset, col_index in assets.items():
        is_continuous_buying = detect_continuous_trend(processed_data, col_index, trend='buy', days=3)
        is_continuous_selling = detect_continuous_trend(processed_data, col_index, trend='sell', days=3)
        if is_continuous_buying and not is_continuous_selling:
            trend_analysis_msg += f"*{message_count}*) Continuous buying detected for {asset} over the last 3 days.\n"
            message_count += 1
        elif is_continuous_selling and not is_continuous_buying:
            trend_analysis_msg += f"*{message_count}*) Continuous selling detected for {asset} over the last 3 days.\n"
            message_count += 1

    # If no continuous trend was detected, add a message indicating no changes
    if not trend_analysis_msg:
        trend_analysis_msg = f"*{message_count}*) No continuous buying or selling detected over the last 3 days.\n"

    # Generate the changes table message
    msg = display_changes_table(changes_table, sorted_data)
    msg += analysis_msg
    msg += "\n" + trend_analysis_msg
    
    stop_docker_container()
    return msg

#if __name__ == "__main__":
    result = get_etf()
   # if result:
       # print("Result:\n", result)
   # else:
      #  print("No result to display.")