/**
 * @file task_queue.c
 * @brief Implements the task queue functions for managing tasks
 */

#include "task_queue.h"
#include "priority.h"

#include <pthread.h>
#include <stdlib.h>

struct queue_node
{
    struct task task;
    uint64_t priority;
    struct queue_node *next;
};

static struct queue_node *head;
static int shutting_down;
static pthread_mutex_t queue_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t queue_cond = PTHREAD_COND_INITIALIZER;

void task_queue_init(void)
{
    pthread_mutex_lock(&queue_mutex);
    head = NULL;
    shutting_down = 0;
    pthread_mutex_unlock(&queue_mutex);
}

void task_queue_destroy(void)
{
    pthread_mutex_lock(&queue_mutex);
    struct queue_node *node = head;
    while (node != NULL)
    {
        struct queue_node *next = node->next;
        free(node);
        node = next;
    }
    head = NULL;
    pthread_mutex_unlock(&queue_mutex);
}

void task_queue_push(struct task task)
{
    struct queue_node *node = malloc(sizeof(*node));
    if (node == NULL)
    {
        return;
    }
    node->task = task;
    node->priority = true_priority(&task);
    node->next = NULL;

    pthread_mutex_lock(&queue_mutex);

    if (head == NULL || node->priority > head->priority)
    {
        node->next = head;
        head = node;
    }
    else
    {
        struct queue_node *current = head;
        while (current->next != NULL && current->next->priority >= node->priority)
        {
            current = current->next;
        }
        node->next = current->next;
        current->next = node;
    }

    pthread_cond_signal(&queue_cond);
    pthread_mutex_unlock(&queue_mutex);
}

int task_queue_pop(struct task *out)
{
    pthread_mutex_lock(&queue_mutex);

    while (head == NULL && !shutting_down)
    {
        pthread_cond_wait(&queue_cond, &queue_mutex);
    }

    if (head == NULL)
    {
        pthread_mutex_unlock(&queue_mutex);
        return -1;
    }

    struct queue_node *node = head;
    head = node->next;
    *out = node->task;

    pthread_mutex_unlock(&queue_mutex);

    free(node);
    return 0;
}

void task_queue_shutdown(void)
{
    pthread_mutex_lock(&queue_mutex);
    shutting_down = 1;
    pthread_cond_broadcast(&queue_cond);
    pthread_mutex_unlock(&queue_mutex);
}
