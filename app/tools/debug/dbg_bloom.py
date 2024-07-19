import asyncio
import hashlib
import os

from services.lib.bloom_filt import BloomFilter
from services.lib.db import DB


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
    n = 10000

    await redis_instance.delete(k)

    bf = BloomFilter(redis_instance, redis_key=k, capacity=10000000, error_rate=0.001)

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

    print(f"False positives: {false_positives}")

    print("Checking true positives...")
    true_positives = 0
    for good_hash in good_hashes:
        if await bf.contains(good_hash):
            true_positives += 1

    print(f"True positives: {true_positives}")

    print(bf)


# Run the example
asyncio.run(main())
