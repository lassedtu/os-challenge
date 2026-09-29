/**
 * @file hash_cache.c
 * @brief Implements the hash cache functions for storing and retrieving hash-number pairs
 */

#include "hash_cache.h"

#include <pthread.h>
#include <string.h>

static struct cache_entry entries[HASH_CACHE_CAPACITY];
static size_t next_index;
static size_t entry_count;
static pthread_mutex_t cache_mutex = PTHREAD_MUTEX_INITIALIZER;

void hash_cache_init(void)
{
    pthread_mutex_lock(&cache_mutex);
    next_index = 0;
    entry_count = 0;
    pthread_mutex_unlock(&cache_mutex);
}

void hash_cache_destroy(void)
{
    pthread_mutex_lock(&cache_mutex);
    next_index = 0;
    entry_count = 0;
    pthread_mutex_unlock(&cache_mutex);
}

int hash_cache_lookup(const unsigned char target[HASH_SIZE], uint64_t *answer_out)
{
    int found = 0;

    pthread_mutex_lock(&cache_mutex);
    for (size_t i = 0; i < entry_count; i++)
    {
        if (memcmp(entries[i].hash, target, HASH_SIZE) == 0)
        {
            *answer_out = entries[i].number;
            found = 1;
            break;
        }
    }
    pthread_mutex_unlock(&cache_mutex);

    return found;
}

void hash_cache_insert(const unsigned char target[HASH_SIZE], uint64_t number)
{
    pthread_mutex_lock(&cache_mutex);
    memcpy(entries[next_index].hash, target, HASH_SIZE);
    entries[next_index].number = number;
    next_index = (next_index + 1) % HASH_CACHE_CAPACITY;
    if (entry_count < HASH_CACHE_CAPACITY)
    {
        entry_count++;
    }
    pthread_mutex_unlock(&cache_mutex);
}
