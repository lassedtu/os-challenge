/**
 * @file worker_pool.h
 * @brief Declares the worker pool functions for managing master/slave worker groups
 */

#ifndef WORKER_POOL_H
#define WORKER_POOL_H

// The number of worker threads is set when the server starts.
// The server counts the CPUs that it can use and starts one thread for each CPU.
// The server VM can have 4 to 16 CPUs, thus a fixed number of threads is not correct for all VMs.
//
// Two values can be set at compile time for experiments (for example -DWORKERS_TOTAL=4):
//   WORKERS_TOTAL  Total number of threads. If you set it, the server does not count the CPUs.
//   MASTER_COUNT   Number of masters. If you do not set it, the server uses DEFAULT_MASTER_COUNT.
// The threads are divided between the masters. If the division is not equal, the first groups get one more thread.

// Number of masters when MASTER_COUNT is not set.
// Each master gets tasks from the priority queue and splits each request between the threads of its group.
#define DEFAULT_MASTER_COUNT 2

/**
 * @brief Starts the worker pool, creating all master and slave threads
 */
void worker_pool_start(void);

/**
 * @brief Joins the worker pool, waking and joining all master and slave threads
 */
void worker_pool_join(void);

#endif
