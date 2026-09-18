/**
 * @file hashing.c
 * @brief Implements the hashing logic for the server
 */

#define LONESHA256_STATIC
#include "lonesha256.h"
#include "hashing.h"
#include "hash_compare.h"
#include "messages.h"

/**
 * @brief Computes the SHA-256 hash of a given 64-bit number with lonesha256
 * @param number The 64-bit number to hash
 * @param output The output buffer to store the resulting hash (32 bytes)
 */
static void hash_of_number(uint64_t number, uint8_t output[HASH_SIZE])
{
    uint64_t little_endian_number = htole64(number);
    lonesha256(output, (const unsigned char *)&little_endian_number, sizeof(little_endian_number));
}

// linear solution for now (testing purposes)
int find_hash_answer(const unsigned char target[32], uint64_t start, uint64_t end, uint64_t *answer)
{
    uint8_t candidate_hash[HASH_SIZE];

    for (uint64_t number = start; number < end; number++)
    {
        hash_of_number(number, candidate_hash);

        if (hash_equal(candidate_hash, target))
        {
            *answer = number;
            return 0;
        }
    }

    // if the algorithm found no match return start
    *answer = start;
    return -1;
}
