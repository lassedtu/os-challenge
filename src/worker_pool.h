/**
 * @file worker_pool.h
 * @brief Declares the worker pool functions for managing worker threads
 */

#ifndef WORKER_POOL_H
#define WORKER_POOL_H

// Defines the number of worker threads in the pool
#define WORKER_COUNT 2

/**
 * @brief Starts the worker pool
 */
void worker_pool_start(void);

/**
 * @brief Joins the worker pool
 */
void worker_pool_join(void);

#endif
