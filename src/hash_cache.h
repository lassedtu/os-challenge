/**
 * @file hash_cache.h
 * @brief Declares the hash cache functions for storing and retrieving hash-number pairs
 */

#ifndef HASH_CACHE_H
#define HASH_CACHE_H

#include "hash_compare.h"

#include <stdint.h>

// Capacity of the hash cache
#define HASH_CACHE_CAPACITY 1024

/**
 * @struct cache_entry
 * @brief Represents a single entry in the hash cache
 */
struct cache_entry
{
    unsigned char hash[HASH_SIZE];
    uint64_t number;
};

/**
 * @brief Initializes the hash cache
 */
void hash_cache_init(void);

/**
 * @brief Destroys the hash cache
 */
void hash_cache_destroy(void);

/**
 * @brief Looks up a hash in the cache and retrieves the associated number if found
 * @param target The hash to look up in the cache
 * @param answer_out Pointer to store the associated number if the hash is found
 */
int hash_cache_lookup(const unsigned char target[HASH_SIZE], uint64_t *answer_out);

/**
 * @brief Inserts a hash-number pair into the cache, replacing the oldest entry if the cache is full
 * @param target The hash to insert into the cache
 * @param number The number associated with the hash to insert into the cache
 */
void hash_cache_insert(const unsigned char target[HASH_SIZE], uint64_t number);

#endif
