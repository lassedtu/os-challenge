/**
 * @file hash_compare.c
 * @brief Implements SHA-256 hash comparison
 */

#include "hash_compare.h"

#include <string.h>

// simple byte-wise comparison of two hashes for now
int hash_equal(const uint8_t left[HASH_SIZE], const uint8_t right[HASH_SIZE])
{
    return memcmp(left, right, HASH_SIZE) == 0;
}
