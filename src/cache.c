#include "cache.h"
#include <string.h>
#include <stdio.h>

void cache_init(cache_t *cache) {
    cache->count = 0;

    pthread_mutex_init(&cache->mutex, NULL);
}



int cache_lookup(
    cache_t *cache,
    const unsigned char hash[32],
    uint64_t start,
    uint64_t end,
    uint64_t *answer
) {
    pthread_mutex_lock(&cache->mutex);

    for (int i = 0; i < cache->count; i++) {
        cache_entry_t *entry = &cache->entries[i];

        if (entry->start == start && entry->end == end && memcmp(entry->hash, hash, 32) == 0) {
            *answer = entry->answer;
            entry->hits ++;

            if (entry->hits >= CACHE_REPEAT_LIMIT) {
                cache_delete(cache, i);
            }

            pthread_mutex_unlock(&cache->mutex);
            return 1;
        }
    }

    pthread_mutex_unlock(&cache->mutex);
    return 0;
}

void cache_delete(cache_t *cache, int index) {
    if (index < 0 || index >= cache->count) {
        return;
    }

    printf(" --> CACHE REMOVAL\n");

    cache->count--;

    if (index != cache->count) {
        memcpy(
            &cache->entries[index],
            &cache->entries[cache->count],
            sizeof(cache_entry_t)
        );
    }
}

void cache_insert(
    cache_t *cache,
    const unsigned char hash[32],
    uint64_t start,
    uint64_t end,
    uint64_t answer
) {
    pthread_mutex_lock(&cache->mutex);

    if (cache->count < CACHE_SIZE) {
        cache_entry_t *entry = &cache->entries[cache->count];

        memcpy(entry->hash, hash, 32);
        entry->answer = answer;
        entry->start = start;
        entry->end = end;
        entry->hits = 0;

        cache->count ++;
    }

    pthread_mutex_unlock(&cache->mutex);
}
