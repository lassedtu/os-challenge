#pragma once

#include <stdint.h>
#include <pthread.h>

#define CACHE_SIZE 1024
#define CACHE_REPEAT_LIMIT 4



typedef struct {
    unsigned char hash[32];
    uint64_t answer;
    uint64_t start;
    uint64_t end;
    uint16_t hits;
} cache_entry_t;


typedef struct {
    cache_entry_t entries[CACHE_SIZE];
    int count;
    pthread_mutex_t mutex;
} cache_t;


void cache_init(cache_t *cache);


int cache_lookup(
    cache_t *cache,
    const unsigned char hash[32],
    uint64_t start,
    uint64_t end,
    uint64_t *answer
);


void cache_insert(
    cache_t *cache,
    const unsigned char hash[32],
    uint64_t start,
    uint64_t end,
    uint64_t answer
);

void cache_delete(
    cache_t *cache,
    int index
);
