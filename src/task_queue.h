/**
 * @file task_queue.h
 * @brief Declares the task queue functions for managing tasks
 */

#ifndef TASK_QUEUE_H
#define TASK_QUEUE_H

#include <stdint.h>

/**
 * @brief Represents a task to be processed by the worker threads
 */
struct task
{
    int client_fd;    // File descriptor for the client connection associated with this task
    uint8_t priority; // Priority byte (higher value = higher priority)
};

/**
 * @brief Initializes the task queue
 */
void task_queue_init(void);

/**
 * @brief Destroys the task queue
 */
void task_queue_destroy(void);

/**
 * @brief Pushes a new task onto the task queue, maintaining priority order
 * @param task The task to be added to the queue
 */
void task_queue_push(struct task task);

/**
 * @brief Pops a task from the task queue, blocking if the queue is empty until a task is available or shutdown is requested
 * @param out Pointer to a task structure where the popped task will be stored
 * @return 0 if a task was successfully popped, -1 if the queue is empty and shutdown has been requested
 */
int task_queue_pop(struct task *out);

/**
 * @brief Signals the task queue to shut down, waking up any waiting threads and preventing further task processing
 */
void task_queue_shutdown(void);

#endif
