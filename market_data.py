import requests
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime


CACHE_FILE = "market_cache.json"

# Shared headers for all warframe.market API requests
HEADERS = {
    "Accept": "application/json",
    "Language": "en",
    "Platform": "pc",
    "Crossplay": "true",
    "User-Agent": "WFV74"
}


# =============================================================================
# API FETCHING
# =============================================================================

def fetch_all_items():
    """
    Fetch the full item catalog from warframe.market and return
    only prime-related items (parts AND sets).

    Returns a list of dicts, each with:
        - "name": display name (e.g. "Rhino Prime Chassis")
        - "slug": the API's own URL slug (e.g. "rhino_prime_chassis")

    We use the slug from the API directly instead of constructing it
    from the name, because the API's slug doesn't always match a
    simple name-to-slug conversion.
    """
    url = "https://api.warframe.market/v2/items"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    data = response.json()

    all_items = data["data"]

    # Keep anything with " Prime " in the name — this includes both
    # individual parts (Chassis, Blade, etc.) and full sets.
    # Store both the display name and the API's slug.
    prime_items = [
        {
            "name": item["i18n"]["en"]["name"],
            "slug": item["slug"]
        }
        for item in all_items
        if " prime " in item["i18n"]["en"]["name"].lower()
    ]

    # Sort by display name for consistent ordering
    prime_items.sort(key=lambda x: x["name"])
    return prime_items


def fetch_best_buy_price(slug, display_name="", max_retries=3):
    """
    Fetch the highest online buy order price for a single item.
    Uses the item's API slug (not a constructed URL) for the request.

    Returns the price in platinum, or None if no online buyers exist.
    Retries with exponential backoff if we get rate limited (429).
    """
    orders_url = f"https://api.warframe.market/v2/items/{slug}/orders"

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(orders_url, headers=HEADERS)

            # If rate limited, wait longer on each retry and try again
            if response.status_code == 429:
                if attempt < max_retries:
                    wait_time = 2 ** (attempt + 1)  # 2s, 4s, 8s
                    print(f"  Rate limited on {display_name}, waiting {wait_time}s (attempt {attempt + 1})...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"  Rate limited on {display_name}, giving up after {max_retries} retries.")
                    return None

            response.raise_for_status()
            data = response.json()

            # Only consider buy orders from users who are currently online
            buy_orders = [
                order["platinum"]
                for order in data["data"]["orders"]
                if order["user"]["status"] != "offline"
                and order["order_type"] == "buy"
            ]

            return max(buy_orders) if buy_orders else None

        except Exception as e:
            print(f"  Error fetching price for {display_name} ({slug}): {e}")
            return None

    return None


# =============================================================================
# SET GROUPING
# =============================================================================

def get_set_prefix(item_name):
    """
    Extract the set prefix from an item name — everything before ' Prime '.
    This is used to group items that belong to the same prime set.

    Examples:
        'Rhino Prime Chassis'       → 'Rhino'
        'Nami Skyla Prime Blade'    → 'Nami Skyla'
        'Silva & Aegis Prime Set'   → 'Silva & Aegis'
        'Dual Kamas Prime Handle'   → 'Dual Kamas'
    """
    parts = item_name.split(" Prime ")
    return parts[0] if parts else item_name


def group_into_sets(prime_items):
    """
    Group a list of prime item dicts into sets by their prefix.
    Each item dict has "name" and "slug" keys.
    """
    sets = {}
    for item in prime_items:
        prefix = get_set_prefix(item["name"])
        if prefix not in sets:
            sets[prefix] = []
        sets[prefix].append(item)
    return sets


# =============================================================================
# MAIN FETCH + CACHE
# =============================================================================

def fetch_all_prices(progress_callback=None, batch_size=3, batch_delay=1.0):
    """
    Fetch all prime items and their best buy prices, grouped by set.
    This is the main function called at app startup.

    Fetches prices in small batches with a delay between each batch.
    Default of 3 per batch with 1s delay respects the official
    warframe.market rate limit of 3 requests per second.

    Args:
        progress_callback: Optional function(current, total, item_name)
                          called after each item's price is fetched.
                          Useful for updating a loading bar in the GUI.
        batch_size:        How many price requests to send at once (default 3).
        batch_delay:       Seconds to wait between batches (default 1.0).

    Returns:
        dict with structure:
        {
            "timestamp": "2026-03-31T...",
            "sets": {
                "Rhino": [
                    {"name": "Rhino Prime Blueprint", "slug": "...", "best_buy_price": 10},
                    ...
                ],
                ...
            }
        }
    """
    # Step 1: Get all prime items (name + slug) from warframe.market
    print("Fetching item list from warframe.market...")
    all_prime_items = fetch_all_items()
    total = len(all_prime_items)
    print(f"Found {total} prime items (including sets).")

    # Step 2: Group items by their set prefix
    grouped = group_into_sets(all_prime_items)
    print(f"Grouped into {len(grouped)} sets.")

    # Step 3: Fetch prices in small batches with pauses between each batch.
    # Official rate limit is 3 requests/second, so batch_size=3 + 1s delay.
    print(f"Fetching prices ({batch_size} at a time, {batch_delay}s between batches)...")
    prices = {}  # slug → best_buy_price
    completed = 0

    for i in range(0, total, batch_size):
        batch = all_prime_items[i:i + batch_size]

        # Fetch this batch concurrently
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            future_to_item = {
                executor.submit(fetch_best_buy_price, item["slug"], item["name"]): item
                for item in batch
            }

            for future in as_completed(future_to_item):
                item = future_to_item[future]
                price = future.result()
                prices[item["slug"]] = price
                completed += 1

                if progress_callback:
                    progress_callback(completed, total, item["name"])

        # Pause between batches to stay under the rate limit
        if i + batch_size < total:
            time.sleep(batch_delay)

    # Step 4: Build the final data structure, sorted by prefix and item name
    sets_data = {}
    for prefix in sorted(grouped.keys()):
        items_in_set = grouped[prefix]
        sets_data[prefix] = []
        for item in sorted(items_in_set, key=lambda x: x["name"]):
            sets_data[prefix].append({
                "name": item["name"],
                "slug": item["slug"],
                "best_buy_price": prices.get(item["slug"])
            })

    cache = {
        "timestamp": datetime.now().isoformat(),
        "sets": sets_data
    }

    print(f"Done. Fetched prices for {total} items across {len(sets_data)} sets.")
    return cache


# =============================================================================
# CACHE FILE I/O
# =============================================================================

def save_cache(cache_data, filepath=CACHE_FILE):
    """Save the price data to a local JSON file."""
    with open(filepath, "w") as f:
        json.dump(cache_data, f, indent=2)
    print(f"Cache saved to {filepath}")


def load_cache(filepath=CACHE_FILE):
    """Load cached price data from JSON. Returns None if file doesn't exist."""
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r") as f:
        return json.load(f)


# =============================================================================
# LOOKUP HELPERS
# =============================================================================

def lookup_by_prefix(cache_data, search_term):
    """
    Find all sets whose prefix matches the search term.
    Case-insensitive. Matches if the search term equals or appears
    within the prefix (so 'Rhin' would still match 'Rhino').

    Returns a dict of matching prefix → item list.
    """
    results = {}
    search_lower = search_term.lower()
    for prefix, items in cache_data["sets"].items():
        if search_lower in prefix.lower():
            results[prefix] = items
    return results


def find_sets_from_words(cache_data, ocr_words):
    """
    Given a list of words from OCR output, find which prime sets match.
    A set matches if any word from OCR matches a word in its prefix.

    For example, if OCR produces ['Rhino', 'Galatine', 'junk'], this
    returns the data for both the Rhino and Galatine prime sets.

    Returns a dict of matching prefix → item list.
    """
    results = {}
    # Build a lookup of individual prefix words → full prefix
    # e.g. 'Nami' → 'Nami Skyla', 'Skyla' → 'Nami Skyla'
    word_to_prefix = {}
    for prefix in cache_data["sets"].keys():
        for word in prefix.split():
            word_to_prefix[word.lower()] = prefix

    for ocr_word in ocr_words:
        cleaned = ocr_word.strip().lower()
        if cleaned in word_to_prefix:
            prefix = word_to_prefix[cleaned]
            if prefix not in results:
                results[prefix] = cache_data["sets"][prefix]

    return results


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    # When run directly, fetch everything and save to JSON
    def print_progress(current, total, name):
        print(f"  [{current}/{total}] {name}")

    cache = fetch_all_prices(progress_callback=print_progress)
    save_cache(cache)

    # Quick test: look up a set by prefix
    print("\n--- Test lookup: 'Rhino' ---")
    results = lookup_by_prefix(cache, "Rhino")
    for prefix, items in results.items():
        print(f"\n{prefix} Prime:")
        for item in items:
            price = item["best_buy_price"]
            price_str = f"{price}p" if price is not None else "no buyers"
            print(f"  {item['name']} ({item['slug']}): {price_str}")

    # Quick test: simulate OCR words
    print("\n--- Test OCR match: ['Rhino', 'Galatine', 'garbage'] ---")
    ocr_results = find_sets_from_words(cache, ["Rhino", "Galatine", "garbage"])
    for prefix, items in ocr_results.items():
        print(f"\n{prefix} Prime:")
        for item in items:
            price = item["best_buy_price"]
            price_str = f"{price}p" if price is not None else "no buyers"
            print(f"  {item['name']}: {price_str}")