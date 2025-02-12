import asyncio
import os
from dotenv import load_dotenv
from datetime import datetime
from utils.telegram_utils import send_message
from .get_signals import get_signals

# Load environment variables
load_dotenv()
TRADE_CHAT_IDS = os.getenv("TRADE_CHAT_IDS", "").split(",")

async def send_signals():
    print("Starting signals workflow...")

    # Setup logging
    log_dir = "/home/jason/dailybot/logs"
    log_file_path = os.path.join(log_dir, "signals.log")
    os.makedirs(log_dir, exist_ok=True)

    with open(log_file_path, "a") as log_file:
        log_file.write(f"Script started at {datetime.now()}\n")

    try:
        # Get and send signals
        signal = await get_signals()
        if signal:
            await send_message(signal, chat_ids=TRADE_CHAT_IDS)
            print("Signals sent successfully")
        else:
            print("No signals to send")

        print("Signals workflow completed.")
    except Exception as e:
        error_msg = f"Error in signals workflow: {str(e)}"
        print(error_msg)
        with open(log_file_path, "a") as log_file:
            log_file.write(f"{error_msg}\n")

    with open(log_file_path, "a") as log_file:
        log_file.write(f"Script finished at {datetime.now()}\n")

if __name__ == "__main__":
    asyncio.run(send_signals())
