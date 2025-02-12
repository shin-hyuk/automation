import btc
import crypto

def get_daily1():
    msg = btc.get_distribution()
    # msg += "\n" + crypto.get_google_trends()
    # msg += "\n" + crypto.get_greed_fear_index()
    # msg += "\n" + crypto.get_order_book()

    return msg
