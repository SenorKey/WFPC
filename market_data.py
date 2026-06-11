import requests
import json
import os
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime


CACHE_FILE = "market_cache.json"

# Shared headers for all warframe.market API requests
HEADERS = {
    "Accept": "application/json",
    "Language": "en",
    "Platform": "pc",
    "Crossplay": "true",
    "User-Agent": "WFPC"
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
    response = requests.get(url, headers=HEADERS, timeout=15)
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


# Returned for any item whose orders couldn't be fetched (network error,
# rate limit exhaustion). Treated as "no price, no offers" downstream.
_EMPTY_ORDER_INFO = {"best_buy_price": None, "buy_count": 0, "sell_count": 0}


def fetch_top_orders(slug, display_name="", max_retries=3):
    """
    Fetch order info for a single item using the /top endpoint.

    The /top endpoint returns the top (up to) 5 buy and 5 sell orders
    from NON-OFFLINE users only, pre-sorted by price. Because it's
    capped at 5 and already excludes offline users, the length of each
    list is min(actual non-offline orders, 5) — so a count of 5 means
    "5 or more non-offline offers exist", which is exactly the liquidity
    signal we use to filter the top-items panel.

    Returns a dict:
        {
            "best_buy_price": highest non-offline buy price (plat) or None,
            "buy_count":      number of non-offline buy orders (0-5),
            "sell_count":     number of non-offline sell orders (0-5),
        }
    Retries with exponential backoff if we get rate limited (429).
    """
    # Correct v2 endpoint: /v2/orders/item/{slug}/top
    orders_url = f"https://api.warframe.market/v2/orders/item/{slug}/top"

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(orders_url, headers=HEADERS, timeout=10)

            # If rate limited, wait longer on each retry and try again
            if response.status_code == 429:
                if attempt < max_retries:
                    wait_time = 2 ** (attempt + 1)  # 2s, 4s, 8s
                    print(f"  Rate limited on {display_name}, waiting {wait_time}s (attempt {attempt + 1})...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"  Rate limited on {display_name}, giving up after {max_retries} retries.")
                    return dict(_EMPTY_ORDER_INFO)

            response.raise_for_status()
            data = response.json()

            # The /top endpoint returns: { "buy": [...], "sell": [...] }
            # Buy orders are sorted by price (highest first).
            buy_orders = data["data"].get("buy", [])
            sell_orders = data["data"].get("sell", [])

            return {
                # First buy order is the best price since they're pre-sorted
                "best_buy_price": buy_orders[0]["platinum"] if buy_orders else None,
                "buy_count": len(buy_orders),
                "sell_count": len(sell_orders),
            }

        except Exception as e:
            print(f"  Error fetching orders for {display_name} ({slug}): {e}")
            return dict(_EMPTY_ORDER_INFO)

    return dict(_EMPTY_ORDER_INFO)


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

    Uses the /v2/orders/item/{slug}/top endpoint which returns only
    the top 5 buy/sell orders per item (much lighter than all orders).

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
    # One executor is reused for all batches to avoid spinning up a new
    # thread pool every iteration.
    print(f"Fetching prices ({batch_size} at a time, {batch_delay}s between batches)...")
    order_info = {}  # slug → {"best_buy_price", "buy_count", "sell_count"}
    completed = 0

    with ThreadPoolExecutor(max_workers=batch_size) as executor:
        for i in range(0, total, batch_size):
            batch = all_prime_items[i:i + batch_size]

            # Submit this batch of requests
            future_to_item = {
                executor.submit(fetch_top_orders, item["slug"], item["name"]): item
                for item in batch
            }

            # Wait for all futures in this batch to finish before moving on
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                order_info[item["slug"]] = future.result()
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
            info = order_info.get(item["slug"], _EMPTY_ORDER_INFO)
            sets_data[prefix].append({
                "name": item["name"],
                "slug": item["slug"],
                "best_buy_price": info.get("best_buy_price"),
                "buy_count": info.get("buy_count", 0),
                "sell_count": info.get("sell_count", 0),
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


def _normalize_name(text):
    """
    Collapse a name to a comparison key: strip accents, lowercase, and
    drop everything that isn't a letter or digit (spaces, '&', punctuation).

    This makes matching tolerant of the OCR quirk where spaces between
    words go missing — 'Braton Prime Stock' and 'BratonPrimeStock' both
    normalize to 'bratonprimestock'.
    """
    decomposed = unicodedata.normalize("NFD", text)
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in no_accents.lower() if c.isalnum())


def _bbox(box):
    """Axis-aligned bounds (x0, y0, x1, y1) of a 4-point OCR box."""
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return (min(xs), min(ys), max(xs), max(ys))


def _x_overlap(a, b):
    """Width of the horizontal overlap between two bboxes (<=0 if none)."""
    return min(a[2], b[2]) - max(a[0], b[0])


def find_items_from_boxes(cache_data, detections):
    """
    Match OCR detections to the specific reward items they name, and
    return per-reward price info.

    Each detection is a (box, text, score) tuple as returned by
    read_ss.read_boxes, where box is four [x, y] corner points.

    Matching keys off the full item name including its part descriptor,
    so a reward of 'Braton Prime Stock' resolves to that exact part rather
    than just the Braton set. It is space/case/accent-insensitive (see
    _normalize_name), so dropped OCR spaces still match.

    Two passes:
      1. Match each detection on its own.
      2. Stitch together leftovers from a name that wrapped onto two (or
         more) lines. A wrapped name shows up as vertically stacked,
         horizontally overlapping boxes (e.g. 'Sevagoth Prime Systems'
         above 'Blueprint'); each leftover is grown downward — while it
         still spells the start of a real item name — until the combined
         text completes one.

    The full 'Set' listings are excluded as match candidates — relic
    rewards are always individual parts — but each matched part is paired
    with its set's buy price for display.

    Returns a list of dicts (deduped by item, in the order first seen):
        {
            "name":          full item name, e.g. 'Braton Prime Stock',
            "buy_price":     the item's best buy price (or None),
            "set_name":      the set prefix, e.g. 'Braton',
            "set_buy_price": the 'Braton Prime Set' buy price (or None),
        }
    """
    # Build normalized full item name -> (item, prefix), and remember each
    # set's buy price by prefix. Skip the 'Set' entries as match targets.
    norm_to_entry = {}
    set_price_by_prefix = {}
    for prefix, items in cache_data["sets"].items():
        for item in items:
            if "Set" in item["name"]:
                set_price_by_prefix[prefix] = item["best_buy_price"]
                continue
            norm_to_entry[_normalize_name(item["name"])] = (item, prefix)

    norm_names = list(norm_to_entry)
    # Longest names first so a box matches the most specific item.
    names_by_len = sorted(norm_names, key=len, reverse=True)

    seen = set()
    results = []

    def add_match(entry):
        item, prefix = entry
        if item["slug"] in seen:
            return
        seen.add(item["slug"])
        results.append({
            "name": item["name"],
            "buy_price": item["best_buy_price"],
            "set_name": prefix,
            "set_buy_price": set_price_by_prefix.get(prefix),
        })

    def contained_entry(s):
        """The (item, prefix) for the longest full name contained in s, if any."""
        for name in names_by_len:
            if name in s:
                return norm_to_entry[name]
        return None

    def is_name_prefix(s):
        """True if s is the leading part of some full item name."""
        return any(name.startswith(s) for name in norm_names)

    # --- Pass 1: match each detection on its own ---
    leftovers = []  # [bbox, normalized_text] for fragments that didn't match
    for box, text, _score in detections:
        norm = _normalize_name(text)
        if not norm:
            continue
        # A single box usually holds one reward name, but checking every
        # candidate (rather than stopping at the first) also handles a box
        # that merged two reward names together.
        contained = [name for name in names_by_len if name in norm]
        if contained:
            for name in contained:
                add_match(norm_to_entry[name])
        else:
            leftovers.append([_bbox(box), norm])

    # --- Pass 2: stitch wrapped names back together from the leftovers ---
    # Process top-to-bottom, left-to-right so a head line is seen before
    # its continuation line.
    order = sorted(
        range(len(leftovers)),
        key=lambda k: (leftovers[k][0][1], leftovers[k][0][0]),
    )
    used = set()
    for i in order:
        if i in used:
            continue
        head_bbox, acc = leftovers[i]
        if not is_name_prefix(acc):
            continue  # not the beginning of any item name — almost certainly junk

        chain = [i]
        last_bbox = head_bbox
        entry = contained_entry(acc)

        while entry is None:
            # Find the nearest unused leftover sitting directly below the
            # current box and overlapping it horizontally — the next
            # wrapped line of the same name.
            line_h = max(1, last_bbox[3] - last_bbox[1])
            best, best_top = None, None
            for j in order:
                if j in used or j in chain:
                    continue
                cb = leftovers[j][0]
                below = cb[1] >= (last_bbox[1] + last_bbox[3]) / 2
                near = (cb[1] - last_bbox[3]) <= line_h
                if below and near and _x_overlap(last_bbox, cb) > 0:
                    if best_top is None or cb[1] < best_top:
                        best_top, best = cb[1], j
            if best is None:
                break

            candidate = acc + leftovers[best][1]
            ce = contained_entry(candidate)
            if ce is None and not is_name_prefix(candidate):
                break  # this continuation doesn't lead toward a real name
            acc = candidate
            chain.append(best)
            last_bbox = leftovers[best][0]
            entry = ce

        if entry is not None:
            add_match(entry)
            used.update(chain)

    return results


def top_priced_parts(cache_data, n=5, min_buy_offers=5):
    """
    Return the n highest-priced individual prime parts across the whole
    cache, sorted by best buy price (highest first).

    Filtering rules:
      - Full "Set" entries are excluded: relics drop individual parts,
        not assembled sets, so a farmer cares about valuable *parts*.
      - Items with no buy price (best_buy_price is None) are skipped.
      - Items with fewer than `min_buy_offers` non-offline buy orders are
        skipped. "buy_count" comes from the /top endpoint, which only
        counts non-offline users and caps at 5, so the default of 5 means
        "at least 5 active buyers" — a liquidity filter that keeps the
        panel from surfacing items whose high price rests on one or two
        thin orders.

    Cache entries from before the buy_count field existed default to 0,
    so they're filtered out until the data is refreshed.

    Each returned dict is the item dict stored in the cache
    ("name", "slug", "best_buy_price", "buy_count", "sell_count").
    """
    items = [
        item
        for set_items in cache_data["sets"].values()
        for item in set_items
        if item["best_buy_price"] is not None
        and "Set" not in item["name"]
        and item.get("buy_count", 0) >= min_buy_offers
    ]
    items.sort(key=lambda x: x["best_buy_price"], reverse=True)
    return items[:n]


def break_down_set(items):
    """
    Given a list of items belonging to one prime set, separate the
    individual parts from the full set listing and compute the
    sum of individual part buy prices.

    The GUI uses this to show whether it's cheaper to buy parts
    individually or as a complete set.

    Returns a dict with:
        - "parts":      list of individual part items (excludes the Set entry)
        - "set_item":   the Set entry dict, or None if not found
        - "parts_sum":  sum of all part best_buy_prices, or None if any are missing
    """
    # The set entry has "Set" in the name (e.g. "Rhino Prime Set")
    parts = [item for item in items if "Set" not in item["name"]]
    set_item = next((item for item in items if "Set" in item["name"]), None)

    # Sum up part prices — only if every part has a price
    part_prices = [p["best_buy_price"] for p in parts if p["best_buy_price"] is not None]
    # If all parts have prices, sum them; otherwise None to indicate incomplete data
    parts_sum = sum(part_prices) if len(part_prices) == len(parts) else None

    return {
        "parts": parts,
        "set_item": set_item,
        "parts_sum": parts_sum,
    }


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
            print(f"  {item['name']}: {price_str}")

    # Quick test: simulate OCR detections → specific item matching.
    # Detections are (box, text, score); box is four [x, y] corners.
    print("\n--- Test item match: per-reward detections (incl. dropped spaces) ---")

    def _det(text, x, y, w=200, h=30):
        return ([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], text, 0.9)

    detections = [
        _det("Rhino Prime Blueprint", 0, 0),
        _det("GalatinePrimeBlade", 220, 0),
        _det("garbage", 440, 0),
    ]
    for r in find_items_from_boxes(cache, detections):
        ip = r["buy_price"]
        sp = r["set_buy_price"]
        ip_str = f"{ip}p" if ip is not None else "no buyers"
        sp_str = f"{sp}p" if sp is not None else "no buyers"
        print(f"  {r['name']}: item {ip_str} | {r['set_name']} set {sp_str}")