import requests

#get all prime items from the api
def get_prime_items():
    url = "https://api.warframe.market/v2/items"
    headers = {
        "Accept": "application/json",
        "Language": "en",
        "Platform": "pc",
        "Crossplay": "true",
        "User-Agent": "WFV74"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    print(data["data"][0])


    
    all_items = data["data"]
    all_prime_items = [item["i18n"]["en"]["name"] for item in all_items if is_prime_item(item["i18n"]["en"]["name"])]
    all_prime_items.sort()
    return all_prime_items  
    

#check if the item is a prime item and not a set
#we need this because some items on warframe.market aren't primes and some are also sold as sets and show up as items in my list.
def is_prime_item(item_name):
    name_lower = item_name.lower()
    return " prime " in name_lower and " set" not in name_lower

#get only the first word from each item in a list of items.
def get_first_word(items):
    new_items = ["beginning"]
    for item in items:
        if item.split(" ")[0] != new_items[-1]:
            new_items.append(item.split(" ")[0])
    new_items.pop(0)
    return new_items

def get_last_word(items):
    new_items = ["beginning"]
    for item in items:
        if item.split(" ")[-1] != new_items[-1]:
            new_items.append(item.split(" ")[-1])
    new_items.pop(0)
    return new_items
    
#get all individual words from each item in a list of items.
def get_words(items):
    words = []
    for item in items:
        for word in item.split(" "):
            if word not in words:
                words.append(word)
    words.sort()
    return words

#converts item names to urls
def get_urls(items):
    return [item.replace(" ", "_").replace("&", "and").lower() for item in items]

#writes a file containing all possible words from the list of all prime items. This is to help OCR read the item names correctly.
# with open("vocabulary.txt", "w") as file:
#     for word in get_words(get_prime_items()):
#         file.write(word + "\n")


# for word in get_words(get_prime_items()):
#     print(word)

# for i, name in enumerate(get_urls(get_prime_items())):
#         print(f"{i + 1}. {name}")

#for i, name in enumerate(get_prime_items()):
#        print(f"{i + 1}. {name}")

print(get_prime_items())