/**
 * @file worker_pool.h
 * @brief Declares the worker pool functions for managing master/slave worker groups
 */

#ifndef WORKER_POOL_H
#define WORKER_POOL_H

// Total number of worker threads across all groups (matches the machine's core count)
#define WORKERS_TOTAL 16

// Number of master workers; each master pulls tasks from the priority queue
#define MASTER_COUNT 2

// Threads per group, including the master itself (master + slaves)
#define GROUP_SIZE (WORKERS_TOTAL / MASTER_COUNT)

// Number of slave workers owned by each master
#define SLAVES_PER_GROUP (GROUP_SIZE - 1)

/**
 * @brief Starts the worker pool, creating all master and slave threads
 */
void worker_pool_start(void);

/**
 * @brief Joins the worker pool, waking and joining all master and slave threads
 */
void worker_pool_join(void);

#endif
