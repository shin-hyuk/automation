import btc
import crypto

def get_daily1():
    print("\nGenerating daily report (part 1)...")
    try:
        msg = btc.get_distribution()
        msg += "\n" + crypto.get_google_trends()
        msg += "\n" + crypto.get_greed_fear_index()
        msg += "\n" + crypto.get_mining_cost()
        msg += "\n" + crypto.get_order_book()
        print("Daily report (part 1) completed\n")
        return msg
        
    except Exception as e:
        print(f"Failed to generate daily report: {str(e)}\n")
        raise
