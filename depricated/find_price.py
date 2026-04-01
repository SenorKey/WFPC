import requests

def get_price(item_url):
    orders_url = f"https://api.warframe.market/v2/items/{item_url}/orders"
    headers = {
        "Accept": "application/json",
        "Language": "en",
        "Platform": "pc",
        "Crossplay": "true",
        "User-Agent": "WFPC"
    }
    response = requests.get(orders_url, headers=headers)
    response.raise_for_status()
    data = response.json()

    buy_orders = [
        order['platinum']
        for order in data['data']['orders']
        if order['user']['status'] != 'offline' and order['order_type'] == 'buy'
    ]
    return max(buy_orders) if buy_orders else None

def get_item_url(item_name):
    url = item_name.replace(" ", "_").replace("&", "and").replace(" ", "-")
    return url


#TESTING
item = "rhino prime set"
print(get_price(get_item_url(item)))
