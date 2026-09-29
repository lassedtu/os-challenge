/**
 * @file worker_pool.c
 * @brief Implements the worker pool functions for managing worker threads
 */

#include "worker_pool.h"
#include "task_queue.h"
#include "hash_cache.h"
#include "hashing.h"
#include "net_io.h"
#include "protocol.h"
#include "messages.h"

#include <pthread.h>
#include <unistd.h>

static pthread_t workers[WORKER_COUNT];

static void handle_task(int client_fd)
{
    unsigned char request_packet[PACKET_REQUEST_SIZE];
    unsigned char response_packet[PACKET_RESPONSE_SIZE];
    struct request request;
    uint64_t answer;

    if (read_all(client_fd, request_packet, sizeof(request_packet)) == 0 &&
        parse_request(request_packet, &request) == 0)
    {
        if (hash_cache_lookup(request.hash, &answer) == 0)
        {
            if (find_hash_answer(request.hash, request.start, request.end, &answer) == 0)
            {
                hash_cache_insert(request.hash, answer);
            }
        }
        encode_response(answer, response_packet);
        write_all(client_fd, response_packet, sizeof(response_packet));
    }

    close(client_fd);
}

static void *worker_main(void *argument)
{
    (void)argument;

    struct task task;
    while (task_queue_pop(&task) == 0)
    {
        handle_task(task.client_fd);
    }

    return NULL;
}

void worker_pool_start(void)
{
    for (int i = 0; i < WORKER_COUNT; i++)
    {
        pthread_create(&workers[i], NULL, worker_main, NULL);
    }
}

void worker_pool_join(void)
{
    for (int i = 0; i < WORKER_COUNT; i++)
    {
        pthread_join(workers[i], NULL);
    }
}
