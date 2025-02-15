import docker
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import platform
import os
import random
import time
import pymysql
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database Configuration from .env
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
DB_PORT = int(os.getenv('DB_PORT', 3306))

# **📌 Connect to MySQL**
def connect_to_database():
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
        print(f"Database connection error: {e}")
        return None

def initialize_database():
    connection = connect_to_database()
    if not connection:
        return

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS order_book_data (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    date DATE NOT NULL UNIQUE,
                    network_value DECIMAL(20,4) NOT NULL,
                    custody_value DECIMAL(20,4) NOT NULL
                )
            """)
            connection.commit()
            print("Table `order_book_data` is ready.")
    finally:
        connection.close()

def save_to_mysql(network_value, custody_value):
    initialize_database()  # Ensure table exists
    connection = connect_to_database()
    if not connection:
        return

    today_date = datetime.now().strftime("%Y-%m-%d")

    try:
        with connection.cursor() as cursor:
            # Insert new row OR update if the date already exists
            cursor.execute("""
                INSERT INTO order_book_data (date, network_value, custody_value)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                network_value = VALUES(network_value),
                custody_value = VALUES(custody_value)
            """, (today_date, network_value, custody_value))

            connection.commit()
            print(f"MySQL: Data saved (Overwritten if existed) - Date: {today_date}, Network: {network_value}, Custody: {custody_value}")
    finally:
        connection.close()


def get_data_by_date(date):
    connection = connect_to_database()
    if not connection:
        return None
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM order_book_data WHERE date = %s", (date,))
            return cursor.fetchone()
    finally:
        connection.close()

def get_docker_client():
    system = platform.system()
    if system == "Windows":
        os.environ["DOCKER_HOST"] = "npipe:////./pipe/docker_engine"  # Docker Desktop
    elif system == "Linux":
        os.environ["DOCKER_HOST"] = "unix:///var/run/docker.sock"  # Native Docker Engine
    # For Mac, Docker Desktop uses the default setup, no changes needed
    return docker.from_env()

def start_docker_container(container_name, image_name):
    client = docker.from_env()
            
    client.containers.run(
        image_name,
        name=container_name,
        ports={"4444/tcp": 4444},
        detach=True,
    )

def stop_docker_container(container_name):
    client = docker.from_env()

    # Stop the container
    try:
        container = client.containers.get(container_name)
        print(f"Stopping container: {container_name}")
        container.stop()
        container.remove()
    except docker.errors.NotFound:
        print(f"Container {container_name} not found. Skipping stop.")

def extract_numbers_from_content(content):
    soup = BeautifulSoup(content, "html.parser")

    # **Extract Network Value (BTC)**
    network_amount = soup.select_one(".network .network-amount span")
    network_value = network_amount.text.strip()
    network_value_float = float(network_value.replace("WBTC", "").replace(",", "").strip())

    custody_amount = soup.select_one(".custody .btc-usd-amount span")
    custody_value = custody_amount.text.strip()
    custody_value_parts = custody_value.split("  ")
    custody_value_btc = custody_value_parts[0]
    custody_value_usd = custody_value_parts[1]
    custody_value_btc_float = float(custody_value_parts[0].replace("BTC", "").replace(",", "").strip())


    save_to_mysql(network_value_float, custody_value_btc_float)

    return network_value, custody_value_btc, custody_value_usd

def fetch_dynamic_content(url):
    driver = None
    max_retries=10
    success = False
    retries = 0

    while not success and retries < max_retries:
        try:
            options = webdriver.ChromeOptions()
            options.add_argument("--headless")  # Run without GUI
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            path = "http://localhost:4444/wd/hub"
            
            driver = webdriver.Remote(
                command_executor=path,
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
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".network .network-amount span"))
        )
        return driver.page_source
    finally:
        driver.quit()

def get_insight():
    today_date = datetime.now().strftime("%Y-%m-%d")
    yesterday_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    today_data = get_data_by_date(today_date)
    yesterday_data = get_data_by_date(yesterday_date)

    if not today_data or not yesterday_data:
        return ""
    
    today_network = today_data["network_value"]
    today_custody = today_data["custody_value"]
    yesterday_network = yesterday_data["network_value"]
    yesterday_custody = yesterday_data["custody_value"]

    network_change = today_network - yesterday_network
    custody_change = today_custody - yesterday_custody

    insights = []
    if custody_change > 0:
        insights.append(f"{custody_change:.4f} BTC was locked in custody, indicating increased demand.")
    elif custody_change < 0:
        insights.append(f"{abs(custody_change):.4f} BTC was withdrawn from custody, suggesting potential selling pressure.")

    if network_change > 0:
        insights.append(f"{network_change:.4f} WBTC was minted, reflecting strong activity in the wrapped BTC market.")
    elif network_change < 0:
        insights.append(f"{abs(network_change):.4f} BTC was redeemed, decreasing WBTC supply and potentially moving to direct BTC holdings.")

    if not insights:
        return "No changes in both custody and network values."
        
    msg = "\n".join(f"*{i + 1})* {line}" for i, line in enumerate(insights) if line.strip())
    msg += "\n"
    return msg  


def format_message(network_value, custody_value_btc, custody_value_usd):
    msg = f"📖 *Order Book*\n"
    msg += "```\n"
    msg += f"{'Network Value':<25}{'Custody Value':<25}\n"
    msg += "-" * 50 + "\n"
    msg += f"{network_value:<25}{custody_value_btc:<25}\n"
    msg += f"{"":<25}{custody_value_usd:<25}\n"
    msg += "```"
    msg += get_insight()
    return msg

def get_order_book():
    container_name = "selenium-chromium"
    image_name = "selenium/standalone-chromium"

    try:
        # Start the Docker container
        start_docker_container(container_name, image_name)
        # Run Selenium automation
        url = "https://wbtc.network/dashboard/order-book"
        content = fetch_dynamic_content(url)
        
        network_value, custody_value_btc, custody_value_usd = extract_numbers_from_content(content)
        msg = format_message(network_value, custody_value_btc, custody_value_usd)
        
        return msg
    finally:
        stop_docker_container(container_name)  # Ensure container is always stopped

if __name__ == "__main__":
    # For testing purposes
    print(get_order_book())