from read_ss import process_output
from all_prime_items import get_first_word, get_last_word, get_prime_items
from read_ss import read_ss, process_output

output = process_output(read_ss("screenshot_test3.png"))
first_words = get_first_word(get_prime_items())
last_words = get_last_word(get_prime_items())

for word in output:
    if word in first_words:
        