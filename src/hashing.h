/**
 * @file hashing.h
 * @brief Declares the hashing functions for the server
 */

#ifndef HASHING_H
#define HASHING_H

#include <signal.h>
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

/**
 * @brief Finds the answer for a given hash within a specified range, aborting early if a cancellation flag is raised by another thread
 *
 * @param target The target hash to find, represented as a 32-byte array
 * @param start The starting value of the range to search (inclusive)
 * @param end The ending value of the range to search (exclusive)
 * @param answer Pointer to store the found answer if successful
 * @param cancel_flag Pointer to a flag that aborts the search when non-zero, may be NULL to disable cancellation
 * @return 0 if the answer was found, -1 if the range was exhausted or the search was cancelled before finding a match
 */
int find_hash_answer_cancellable(const unsigned char target[32], uint64_t start, uint64_t end,
                                 uint64_t *answer, volatile sig_atomic_t *cancel_flag);

#endif
