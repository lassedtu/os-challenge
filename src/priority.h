/**
 * @file priority.h
 * @brief Declares the function for calculating the true priority of a task
 */

#ifndef PRIORITY_H
#define PRIORITY_H

#include "task_queue.h"

#include <stdint.h>

/**
 * @brief Calculates the true priority of a given task
 * @param task Pointer to the task for which to calculate the priority
 * @return The calculated true priority as a 64-bit unsigned integer
 */
uint64_t true_priority(const struct task *task);

#endif
