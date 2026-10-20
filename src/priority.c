/**
 * @file priority.c
 * @brief Implements the function for calculating the true priority of a task
 */

#include "priority.h"

/*
 * The task queue (see task_queue.c) keeps nodes in descending priority order, working on the highest-priority task first.
 *
 * For now the "true" priority is just the clients priority byte (promoted to 64 bits).
 * This gives the queue a key to sort on and can later be extended to factor in range size, age, etc.
 */
uint64_t true_priority(const struct task *task)
{
    return (uint64_t)task->priority;
}
