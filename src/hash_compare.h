/**
 * @file hash_compare.h
 * @brief Declares helpers for comparing SHA-256 hashes.
 */

#ifndef HASH_COMPARE_H
#define HASH_COMPARE_H

#include <stdint.h>

#define HASH_SIZE 32

/**
 * @brief Compare two hash byte arrays
 * @param left First hash
 * @param right Second hash
 * @return 1 when the hashes are equal, otherwise 0
 */
int hash_equal(const uint8_t left[HASH_SIZE], const uint8_t right[HASH_SIZE]);

#endif
