/**
 * @file hashing.h
 * @brief Declares the hashing function for the server
 */

#ifndef HASHING_H
#define HASHING_H

#include <stdint.h>

/**
 * @brief Finds the answer for a given hash within a specified range
 * @param target The target hash to find, represented as a 32-byte array
 * @param start The starting value of the range to search for the hash
 * @param end The ending value of the range to search for the hash
 * @param answer Pointer to store the found answer if successful
 * @return 0 on success, non-zero on failure
 */
int find_hash_answer(const unsigned char target[32], uint64_t start, uint64_t end, uint64_t *answer);

#endif
