import hashlib
import math


class BloomFilter:
    def __init__(self, redis_instance, redis_key='bloom_filter', capacity=1000000, error_rate=0.001):
        self.capacity = capacity
        self.error_rate = error_rate
        self.size = self.get_size(capacity, error_rate)
        self.hash_count = self.get_hash_count(self.size, capacity)
        self.redis = redis_instance
        self.redis_key = redis_key

    @staticmethod
    def get_size(n, p):
        """
        Calculate the size of the bit array (m) for given capacity (n) and false positive probability (p).
        m = -(n * ln(p)) / (ln(2)^2)
        """
        m = -(n * math.log(p)) / (math.log(2) ** 2)
        return int(m)

    @staticmethod
    def get_hash_count(m, n):
        """
        Calculate the number of hash functions (k) for given size of bit array (m) and capacity (n).
        k = (m/n) * ln(2)
        """
        k = (m / n) * math.log(2)
        return int(k)

    @staticmethod
    def get_sha3_hash(item, seed):
        """
        Generate a SHA3-256 hash for the given item with a seed.
        """
        sha3 = hashlib.sha3_256()
        sha3.update(f"{item}{seed}".encode('utf-8'))
        return sha3.hexdigest()

    async def add(self, item):
        """
        Add an item to the Bloom filter.
        """
        for i in range(self.hash_count):
            sha3_hash = self.get_sha3_hash(item, i)
            bit_position = int(sha3_hash, 16) % self.size
            await self.redis.setbit(self.redis_key, bit_position, 1)

    async def contains(self, item):
        """
        Check if an item is in the Bloom filter.
        """
        for i in range(self.hash_count):
            sha3_hash = self.get_sha3_hash(item, i)
            bit_position = int(sha3_hash, 16) % self.size
            if not await self.redis.getbit(self.redis_key, bit_position):
                return False
        return True

    async def bit_count(self):
        """
        Count the number of bits set to 1 in the Bloom filter.
        """
        return await self.redis.bitcount(self.redis_key, )

    async def get_length(self):
        """
        Get the length of the Bloom filter.
        """
        return await self.redis.strlen(self.redis_key)

    def __str__(self):
        """
        Return a string representation of the Bloom filter.
        """
        return f"BloomFilter(key='{self.redis_key}', size={self.size}, hash_count={self.hash_count})"


class BloomFilterV2(BloomFilter):
    def _hashes(self, element):
        """
        Generate k hash values for the given element.

        :param element: The element to hash.
        :return: A generator yielding k hash positions.
        """
        # Ensure the element is a string
        if not isinstance(element, str):
            element = str(element)

        # Compute two base hash values
        h1 = int(hashlib.sha256(element.encode('utf-8')).hexdigest(), 16)
        h2 = int(hashlib.md5(element.encode('utf-8')).hexdigest(), 16)

        # Generate k hash values using double hashing
        for i in range(self.hash_count):
            yield (h1 + i * h2) % self.size

    async def add(self, item):
        for position in self._hashes(item):
            await self.redis.setbit(self.redis_key, position, 1)

    async def contains(self, item):
        for position in self._hashes(item):
            if not await self.redis.getbit(self.redis_key, position):
                return False
        return True
