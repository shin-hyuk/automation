import docker
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import platform
import os
import random
import time
import pymysql
import ccxt
from datetime import datetime, timedelta
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()

# Database Configuration from .env
DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
DB_PORT = int(os.getenv('DB_PORT', 3306))

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
                CREATE TABLE IF NOT EXISTS mining_cost (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    date DATE NOT NULL UNIQUE,
                    mining_cost DECIMAL(20,2) NOT NULL,
                    btc_price DECIMAL(20,2) NOT NULL,
                    cost_ratio DECIMAL(10,4) NOT NULL,
                    valuation VARCHAR(20) NOT NULL
                )
            """)
            connection.commit()
            print("Table `mining_cost` is ready.")
    finally:
        connection.close()

def save_to_mysql(mining_cost, btc_price, cost_ratio, valuation):
    initialize_database()
    connection = connect_to_database()
    if not connection:
        return

    today_date = datetime.now().strftime("%Y-%m-%d")

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO mining_cost (date, mining_cost, btc_price, cost_ratio, valuation)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                mining_cost = VALUES(mining_cost),
                btc_price = VALUES(btc_price),
                cost_ratio = VALUES(cost_ratio),
                valuation = VALUES(valuation)
            """, (today_date, mining_cost, btc_price, cost_ratio, valuation))

            connection.commit()
            print(f"MySQL: Data saved - Date: {today_date}, Mining Cost: {mining_cost}, BTC Price: {btc_price}")
    finally:
        connection.close()

def get_data_by_date(date):
    connection = connect_to_database()
    if not connection:
        return None
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM mining_cost WHERE date = %s", (date,))
            return cursor.fetchone()
    finally:
        connection.close()

def get_docker_client():
    system = platform.system()
    if system == "Windows":
        os.environ["DOCKER_HOST"] = "npipe:////./pipe/docker_engine"
    elif system == "Linux":
        os.environ["DOCKER_HOST"] = "unix:///var/run/docker.sock"
    return docker.from_env()

def start_docker_container(container_name, image_name):
    # First, stop and remove any existing container with the same name
    try:
        stop_docker_container(container_name)
    except Exception as e:
        print(f"Error stopping existing container: {e}")
    
    # Start new container
    client = docker.from_env()
    client.containers.run(
        image_name,
        name=container_name,
        ports={"4444/tcp": 4444},
        detach=True,
    )

def stop_docker_container(container_name):
    client = docker.from_env()
    try:
        container = client.containers.get(container_name)
        print(f"Stopping container: {container_name}")
        container.stop()
        container.remove()
    except docker.errors.NotFound:
        print(f"Container {container_name} not found. Skipping stop.")

def get_btc_price():
    try:
        exchange = ccxt.binance()
        ticker = exchange.fetch_ticker('BTC/USDT')
        return float(ticker['last'])
    except Exception as e:
        print(f"Error getting BTC price: {e}")
        return None

def fetch_dynamic_content(url):
    driver = None
    max_retries = 10
    success = False
    retries = 0

    while not success and retries < max_retries:
        try:
            options = webdriver.ChromeOptions()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            path = "http://localhost:4444/wd/hub"
            
            driver = webdriver.Remote(
                command_executor=path,
                options=options
            )
            success = True
        except Exception as e:
            print(f"Error initializing WebDriver: {type(e).__name__}: {e}")
            retries += 1
            sleep_time = random.randint(1, 10)
            print(f"Attempt {retries}/{max_retries} failed: {e}")
            print(f"Retrying in {sleep_time} seconds...")
            time.sleep(sleep_time)

    try:
        driver.get(url)
        print("Waiting 20 seconds for page to fully load...")
        time.sleep(20)  # Wait for 20 seconds after page load
        
        # Then wait for the specific element
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.item.v-card.v-sheet.theme--light h2"))
        )
        return driver.page_source
    finally:
        if driver:
            driver.quit()

def extract_mining_cost(content):
    """Extract mining cost using BeautifulSoup"""
    soup = BeautifulSoup(content, "html.parser")
    
    # Find all h2 elements within the specified div class
    cost_elements = soup.select("div.item.v-card.v-sheet.theme--light h2")
    
    if len(cost_elements) < 3:
        raise ValueError("Could not find mining cost element")
    
    # Get the third h2 element (Bitcoin Average Mining Costs)
    mining_cost_text = cost_elements[2].text.strip()
    return float(mining_cost_text.replace("$", "").replace(",", "").strip())

def get_valuation_category(cost_ratio):
    if cost_ratio < 0.75:
        return "Strongly Undervalued"
    elif 0.75 <= cost_ratio < 0.95:
        return "Moderately Undervalued"
    elif 0.95 <= cost_ratio <= 1.05:
        return "Fairly Valued"
    elif 1.05 < cost_ratio <= 1.5:
        return "Moderately Overvalued"
    else:  # > 1.5
        return "Strongly Overvalued"

def format_message(mining_cost, btc_price, cost_ratio, valuation):
    # Format numbers with commas
    mining_cost = "{:,}".format(mining_cost)
    btc_price = "{:,}".format(btc_price)
    
    msg = f"⛏️ *Bitcoin Mining Cost*\n"
    msg += "```\n"
    msg += f"{'Mining Cost':<15}{'BTC Price':<15}{'Cost Ratio':<15}{'Valuation':<20}\n"
    msg += "-" * 67 + "\n"
    msg += f"{f'${mining_cost}':<15}{f'${btc_price}':<15}{cost_ratio:<15}{valuation:<20}\n"
    msg += "```"
    return msg

def get_mining_cost():
    container_name = "selenium-chromium"
    image_name = "selenium/standalone-chromium"

    try:
        start_docker_container(container_name, image_name)
        
        # Get mining cost from CCAF
        url = "https://ccaf.io/cbnsi/cbeci/mining_map/mining_data"
        content = fetch_dynamic_content(url)
        mining_cost = int(extract_mining_cost(content))
        
        # Get BTC price
        btc_price = int(get_btc_price())
        if not btc_price:
            return "Error: Could not fetch BTC price"
        
        # Calculate ratio and determine valuation
        cost_ratio = round(mining_cost / btc_price, 2)
        valuation = get_valuation_category(cost_ratio)
        
        # Save to database
        save_to_mysql(mining_cost, btc_price, cost_ratio, valuation)
        
        # Format message
        return format_message(mining_cost, btc_price, cost_ratio, valuation)
        
    except Exception as e:
        print(f"Error in get_mining_cost: {e}")
        return f"Error: {str(e)}"
    finally:
        stop_docker_container(container_name)

if __name__ == "__main__":
    print(get_mining_cost())
