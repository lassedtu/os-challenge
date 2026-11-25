/**
 * @file worker_pool.h
 * @brief Declares the worker pool functions for managing master/slave worker groups
 */

#ifndef WORKER_POOL_H
#define WORKER_POOL_H

// Total number of worker threads across all groups (matches the machine's core count)
// The build can set a different value with -DWORKERS_TOTAL=<n> (see analysis/split_sweep.py)
#ifndef WORKERS_TOTAL
#define WORKERS_TOTAL 16
#endif

// Number of master workers; each master pulls tasks from the priority queue
// The build can set a different value with -DMASTER_COUNT=<n> (see analysis/split_sweep.py)
#ifndef MASTER_COUNT
#define MASTER_COUNT 2
#endif

// Each group must have the same number of threads. Stop the build if this is not true.
#if MASTER_COUNT < 1 || WORKERS_TOTAL < MASTER_COUNT || (WORKERS_TOTAL % MASTER_COUNT) != 0
#error "WORKERS_TOTAL must be a multiple of MASTER_COUNT, and MASTER_COUNT must be 1 or more"
#endif

// Threads per group, including the master itself (master + slaves)
#define GROUP_SIZE (WORKERS_TOTAL / MASTER_COUNT)

// Number of slave workers owned by each master
#define SLAVES_PER_GROUP (GROUP_SIZE - 1)

// Size of the slave array. ISO C does not permit an array of length zero.
// When GROUP_SIZE is 1, the array has one unused element.
#define SLAVE_ARRAY_SIZE (SLAVES_PER_GROUP > 0 ? SLAVES_PER_GROUP : 1)

/**
 * @brief Starts the worker pool, creating all master and slave threads
 */
void worker_pool_start(void);

/**
 * @brief Joins the worker pool, waking and joining all master and slave threads
 */
void worker_pool_join(void);

#endif
