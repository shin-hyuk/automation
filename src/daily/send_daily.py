import asyncio
import os
from dotenv import load_dotenv
from datetime import datetime
from utils.telegram_utils import send_message
from .get_daily1 import get_daily1
from .get_daily2 import get_daily2

# Load environment variables
load_dotenv()
TRADE_CHAT_IDS = os.getenv("DAILY_CHAT_IDS", "").split(",")

async def send_daily():
    print("Starting daily workflows...")

    # Setup logging
    log_dir = "/home/jason/dailybot/logs"
    log_file_path = os.path.join(log_dir, "daily.log")
    os.makedirs(log_dir, exist_ok=True)

    with open(log_file_path, "a") as log_file:
        log_file.write(f"Script started at {datetime.now()}\n")

    try:
        # Send first daily message
        msg = get_daily1()
        await send_message(msg, chat_ids=TRADE_CHAT_IDS)
        print("Daily message 1 sent successfully")

        # Send second daily message
        msg = get_daily2()
        await send_message(msg, chat_ids=TRADE_CHAT_IDS)
        print("Daily message 2 sent successfully")

        print("All daily workflows completed.")
    except Exception as e:
        error_msg = f"Error in daily workflow: {str(e)}"
        print(error_msg)
        with open(log_file_path, "a") as log_file:
            log_file.write(f"{error_msg}\n")

    with open(log_file_path, "a") as log_file:
        log_file.write(f"Script finished at {datetime.now()}\n")

if __name__ == "__main__":
    asyncio.run(send_daily())
