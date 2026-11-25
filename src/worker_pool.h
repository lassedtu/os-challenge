/**
 * @file worker_pool.h
 * @brief Declares the worker pool functions for managing master/slave worker groups
 */

#ifndef WORKER_POOL_H
#define WORKER_POOL_H

// Total number of worker threads in all groups.
// The value is the same as the number of CPUs of the server VM (4), so each thread can have its own core.
// The request splitting sweep on a 4-CPU VM gave the best results with one thread for each core
// (see analysis/split_sweep.py on the request-splitting-analysis branch).
#define WORKERS_TOTAL 4

// Number of master workers. Each master gets tasks from the priority queue.
// 2 masters with 2 threads each (2x2) was equal to the best result (4x1) in the sweep.
// This shape also splits each request in two, which helps when only one request is in the queue.
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
