import os
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
import json
import ccxt
from dotenv import load_dotenv
from utils import send_message
import asyncio

load_dotenv()
TRADE_CHAT_IDS = os.getenv("TRADE_CHAT_IDS", "").split(",")

def get_binance_price(symbol):
    """Get real-time price from Binance."""
    try:
        exchange = ccxt.binance()
        ticker = exchange.fetch_ticker(symbol)
        return float(ticker['last'])
    except Exception as e:
        print(f"Error fetching price from Binance: {e}")
        return None

async def main():
    try:
        # Read input from command line argument
        if len(sys.argv) < 2:
            print("Error: No input data provided")
            sys.exit(1)
            
        input_data = sys.argv[1]
        data = json.loads(input_data)
        
        # Get Upper Band and trend values
        upper_band = float(data['Upper'])
        upper_band = 97000
        
        # Get current price from Binance
        current_price = get_binance_price("BTC/USDT")
        if current_price is None:
            print("Error: Could not fetch current price")
            sys.exit(1)
            
        print(f"Debug Info:")
        print(f"Upper Band: {upper_band:,.2f}")
        print(f"Real-time Price: {current_price:,.2f}")
        print(f"Distance from Upper Band: {((upper_band - current_price) / current_price) * 100:.2f}%")
        
        # Check if price crosses Upper Band
        if current_price >= upper_band:
            
            message = (
                f"🔝 *{data['symbol']}: Market Top Signal*\n\n"
                f"• Current Price: ${current_price:.2f}\n"
                f"• Upper Band: ${upper_band:.2f}\n"
                f"• Deviation: +{((current_price - upper_band) / upper_band * 100):.1f}%\n\n"
                f"*Analysis:*\n"
                f"Consider taking profits at these elevated levels\n"
                f"Market may be overextended \\- Risk of reversal increased"
            )
            print("\nSignal Generated:")
            print(message)
            await send_message(message, chat_ids=TRADE_CHAT_IDS)
        else:
            print("\nNo signal: Price below Upper Band")
            
    except Exception as e:
        print(f"Error processing data: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())