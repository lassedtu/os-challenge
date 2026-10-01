/**
 * @file worker_pool.c
 * @brief Implements master/slave worker groups for parallel range search
 *
 * Each master worker pulls a task from the priority queue, performs the network
 * I/O, and splits the search range across itself and its slave workers. All
 * participants scan their "sub-ranges" concurrently until one finds the answer,
 * at which point a shared cancellation flag is raised so the others stop early.
 */

#include "worker_pool.h"
#include "task_queue.h"
#include "hash_cache.h"
#include "hashing.h"
#include "net_io.h"
#include "protocol.h"
#include "messages.h"

#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>

/**
 * @struct search_job
 * @brief Shared state for a single request being solved by a group
 */
struct search_job
{
    const unsigned char *target;  // Target hash the group is searching for
    volatile sig_atomic_t found;  // Raised once any participant finds the answer
    uint64_t answer;              // The found answer (valid only when found != 0)
    pthread_mutex_t answer_mutex; // Guards the first-finder claim on answer
};

/**
 * @struct slave_ctx
 * @brief Per-slave context and assigned work
 */
struct slave_ctx
{
    struct worker_group *group; // Owning group
    struct search_job *job;     // Current job (NULL when idle)
    uint64_t start;             // Assigned sub-range start (inclusive)
    uint64_t end;               // Assigned sub-range end (exclusive)
    int has_work;               // Set by master when a sub-range is published
    int shutting_down;          // Set during pool teardown
    pthread_mutex_t mutex;      // Guards this mailbox
    pthread_cond_t cond;        // Signals work availability or shutdown
    pthread_t thread;           // The slave thread
};

/**
 * @struct worker_group
 * @brief A master worker and the slave workers it owns
 */
struct worker_group
{
    pthread_t master;                          // The master thread
    struct slave_ctx slaves[SLAVES_PER_GROUP]; // Slave contexts

    int completed;              // Slaves that finished the current job
    pthread_mutex_t done_mutex; // Guards completed
    pthread_cond_t done_cond;   // Signals slave completion to master
};

static struct worker_group groups[MASTER_COUNT];

/**
 * @brief Records the answer if this participant is the first to find it
 * @param job The shared job state
 * @param answer The answer found by the caller
 */
static void claim_answer(struct search_job *job, uint64_t answer)
{
    pthread_mutex_lock(&job->answer_mutex);
    if (!job->found)
    {
        job->answer = answer;
        job->found = 1;
    }
    pthread_mutex_unlock(&job->answer_mutex);
}

/**
 * @brief Scans a sub-range and claims the answer on a hit
 * @param job The shared job state
 * @param start Sub-range start (inclusive)
 * @param end Sub-range end (exclusive)
 */
static void run_search_slice(struct search_job *job, uint64_t start, uint64_t end)
{
    uint64_t answer;
    if (find_hash_answer_cancellable(job->target, start, end, &answer, &job->found) == 0)
    {
        claim_answer(job, answer);
    }
}

/**
 * @brief Slave thread entry point; waits for work, scans its slice, reports done
 * @param argument Pointer to the slave's context
 * @return NULL on thread exit
 */
static void *slave_main(void *argument)
{
    struct slave_ctx *ctx = argument;

    for (;;)
    {
        pthread_mutex_lock(&ctx->mutex);
        while (!ctx->has_work && !ctx->shutting_down)
        {
            pthread_cond_wait(&ctx->cond, &ctx->mutex);
        }

        if (ctx->shutting_down && !ctx->has_work)
        {
            pthread_mutex_unlock(&ctx->mutex);
            break;
        }

        struct search_job *job = ctx->job;
        uint64_t start = ctx->start;
        uint64_t end = ctx->end;
        ctx->has_work = 0;
        pthread_mutex_unlock(&ctx->mutex);

        run_search_slice(job, start, end);

        struct worker_group *group = ctx->group;
        pthread_mutex_lock(&group->done_mutex);
        group->completed++;
        pthread_cond_signal(&group->done_cond);
        pthread_mutex_unlock(&group->done_mutex);
    }

    return NULL;
}

/**
 * @brief Publishes a sub-range to a slave and wakes it
 * @param ctx The target slave context
 * @param job The shared job state
 * @param start Sub-range start (inclusive)
 * @param end Sub-range end (exclusive)
 */
static void dispatch_to_slave(struct slave_ctx *ctx, struct search_job *job, uint64_t start,
                              uint64_t end)
{
    pthread_mutex_lock(&ctx->mutex);
    ctx->job = job;
    ctx->start = start;
    ctx->end = end;
    ctx->has_work = 1;
    pthread_cond_signal(&ctx->cond);
    pthread_mutex_unlock(&ctx->mutex);
}

/**
 * @brief Solves a request by splitting its range across the group
 * @param group The group performing the search
 * @param request The parsed request
 * @param answer_out Pointer to store the resulting answer
 */
static void solve_request(struct worker_group *group, const struct request *request,
                          uint64_t *answer_out)
{
    struct search_job job;
    job.target = request->hash;
    job.found = 0;
    job.answer = request->start;
    pthread_mutex_init(&job.answer_mutex, NULL);

    uint64_t start = request->start;
    uint64_t end = request->end;
    uint64_t total = (end > start) ? (end - start) : 0;

    // Partition [start, end) into GROUP_SIZE contiguous, near-equal slices
    uint64_t base = total / GROUP_SIZE;
    uint64_t remainder = total % GROUP_SIZE;

    uint64_t bounds[GROUP_SIZE + 1];
    bounds[0] = start;
    for (int i = 0; i < GROUP_SIZE; i++)
    {
        uint64_t width = base + ((uint64_t)i < remainder ? 1 : 0);
        bounds[i + 1] = bounds[i] + width;
    }

    group->completed = 0;

    // Slices 1..SLAVES_PER_GROUP go to the slaves, slice 0 is the master's own work
    for (int i = 0; i < SLAVES_PER_GROUP; i++)
    {
        dispatch_to_slave(&group->slaves[i], &job, bounds[i + 1], bounds[i + 2]);
    }

    run_search_slice(&job, bounds[0], bounds[1]);

    // Wait until every slave has reported completion of its slice
    pthread_mutex_lock(&group->done_mutex);
    while (group->completed < SLAVES_PER_GROUP)
    {
        pthread_cond_wait(&group->done_cond, &group->done_mutex);
    }
    pthread_mutex_unlock(&group->done_mutex);

    *answer_out = job.found ? job.answer : request->start;

    pthread_mutex_destroy(&job.answer_mutex);
}

/**
 * @brief Handles a single client task on the given group
 * @param group The group that will process the task
 * @param client_fd The client connection file descriptor
 */
static void handle_task(struct worker_group *group, int client_fd)
{
    unsigned char request_packet[PACKET_REQUEST_SIZE];
    unsigned char response_packet[PACKET_RESPONSE_SIZE];
    struct request request;
    uint64_t answer;

    if (read_all(client_fd, request_packet, sizeof(request_packet)) == 0 &&
        parse_request(request_packet, &request) == 0)
    {
        // hash_cache_lookup returns non-zero on a hit; only search on a miss
        if (!hash_cache_lookup(request.hash, &answer))
        {
            solve_request(group, &request, &answer);
            hash_cache_insert(request.hash, answer);
        }
        encode_response(answer, response_packet);
        write_all(client_fd, response_packet, sizeof(response_packet));
    }

    close(client_fd);
}

/**
 * @brief Master thread entry point; pulls tasks and drives its group
 * @param argument Pointer to the owning worker group
 * @return NULL on thread exit
 */
static void *master_main(void *argument)
{
    struct worker_group *group = argument;

    struct task task;
    while (task_queue_pop(&task) == 0)
    {
        handle_task(group, task.client_fd);
    }

    return NULL;
}

void worker_pool_start(void)
{
    for (int g = 0; g < MASTER_COUNT; g++)
    {
        struct worker_group *group = &groups[g];
        group->completed = 0;
        pthread_mutex_init(&group->done_mutex, NULL);
        pthread_cond_init(&group->done_cond, NULL);

        for (int s = 0; s < SLAVES_PER_GROUP; s++)
        {
            struct slave_ctx *ctx = &group->slaves[s];
            ctx->group = group;
            ctx->job = NULL;
            ctx->start = 0;
            ctx->end = 0;
            ctx->has_work = 0;
            ctx->shutting_down = 0;
            pthread_mutex_init(&ctx->mutex, NULL);
            pthread_cond_init(&ctx->cond, NULL);
            pthread_create(&ctx->thread, NULL, slave_main, ctx);
        }

        pthread_create(&group->master, NULL, master_main, group);
    }
}

void worker_pool_join(void)
{
    // Masters exit once task_queue_pop returns -1 after task_queue_shutdown
    for (int g = 0; g < MASTER_COUNT; g++)
    {
        pthread_join(groups[g].master, NULL);
    }

    // With masters gone, no new work will be dispatched; release the slaves
    for (int g = 0; g < MASTER_COUNT; g++)
    {
        struct worker_group *group = &groups[g];
        for (int s = 0; s < SLAVES_PER_GROUP; s++)
        {
            struct slave_ctx *ctx = &group->slaves[s];
            pthread_mutex_lock(&ctx->mutex);
            ctx->shutting_down = 1;
            pthread_cond_signal(&ctx->cond);
            pthread_mutex_unlock(&ctx->mutex);
        }

        for (int s = 0; s < SLAVES_PER_GROUP; s++)
        {
            struct slave_ctx *ctx = &group->slaves[s];
            pthread_join(ctx->thread, NULL);
            pthread_mutex_destroy(&ctx->mutex);
            pthread_cond_destroy(&ctx->cond);
        }

        pthread_mutex_destroy(&group->done_mutex);
        pthread_cond_destroy(&group->done_cond);
    }
}
