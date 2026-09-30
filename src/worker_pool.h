/**
 * @file worker_pool.h
 * @brief Declares the worker pool functions for managing worker threads
 */

#ifndef WORKER_POOL_H
#define WORKER_POOL_H

// Defines the number of worker threads in the pool
#ifndef WORKER_COUNT
#define WORKER_COUNT 8
#endif

/**
 * @brief Starts the worker pool
 */
void worker_pool_start(void);

/**
 * @brief Joins the worker pool
 */
void worker_pool_join(void);

#endif
