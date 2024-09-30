import asyncio
import hashlib
import os

from lib.bloom_filt import BloomFilter, BloomFilterV2
from lib.db import DB
from notify.dup_stop import BLOOM_TX_CAPACITY, BLOOM_TX_ERROR_RATE


def generate_secure_random_sha3_hash(length=64):
    """
    Generate a secure random SHA-3 hash.

    Parameters:
    - length (int): The length of the random byte sequence. Default is 64.

    Returns:
    - str: The SHA-3 hash of the random byte sequence, encoded as a hexadecimal string.
    """
    # Generate a secure random byte sequence
    random_bytes = os.urandom(length)

    # Create a new SHA-3 hash object
    sha3_hash = hashlib.sha3_256()

    # Update the hash object with the random byte sequence
    sha3_hash.update(random_bytes)

    # Get the hexadecimal representation of the hash
    hash_hex = sha3_hash.hexdigest()

    return hash_hex


# Example usage
async def main():
    db = DB(asyncio.get_event_loop())
    redis_instance = await db.get_redis()
    # redis_instance = redis.from_url('redis://localhost:6379')

    k = 'my_bloom_filter'
    n = 5000

    await redis_instance.delete(k)

    # bf = BloomFilter(redis_instance, redis_key=k, capacity=BLOOM_TX_CAPACITY, error_rate=BLOOM_TX_ERROR_RATE)
    # bf = BloomFilter(redis_instance, redis_key=k, capacity=1000000, error_rate=0.0001)
    bf = BloomFilter(redis_instance, redis_key=k, capacity=100_000_000, error_rate=0.01)
    print(f'Initialized with key={k}, capacity={bf.capacity}, error_rate={bf.error_rate}. Size is {bf.size} bits')

    await bf.add("test_item")
    contains = await bf.contains("test_item")
    print(f"Contains 'test_item': {contains}")

    contains = await bf.contains("nonexistent_item")
    print(f"Contains 'nonexistent_item': {contains}")

    print(f"Generating {n} random hashes for testing...")
    good_hashes = [generate_secure_random_sha3_hash() for _ in range(n)]

    print(f"Generating {n} random hashes for testing...")
    bad_hashes = [generate_secure_random_sha3_hash() for _ in range(n)]

    print("Adding good hashes to the Bloom filter...")
    for good_hash in good_hashes:
        await bf.add(good_hash)

    print("Checking false positives...")
    false_positives = 0
    for bad_hash in bad_hashes:
        if await bf.contains(bad_hash):
            false_positives += 1

    print(f"False positives: {false_positives}. Error rate: {false_positives / n * 100:.2f}%")

    print("Checking true positives...")
    true_positives = 0
    for good_hash in good_hashes:
        if await bf.contains(good_hash):
            true_positives += 1

    print(f"True positives: {true_positives} / {n}")

    print(bf)


# Run the example
asyncio.run(main())
