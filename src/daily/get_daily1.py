import btc
import crypto

def get_daily1():
    msg = btc.get_distribution()
    msg += "\n" + crypto.get_google_trends()
    print("A")
    msg += "\n" + crypto.get_greed_fear_index()
    print("B")
    msg += "\n" + crypto.get_order_book()
    print("C")

    return msg
