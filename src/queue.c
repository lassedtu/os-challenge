#include "queue.h"


void queue_init(client_queue_t *queue) {
    queue->count = 0;

    pthread_mutex_init(&queue->mutex, NULL);
    pthread_cond_init(&queue->not_empty, NULL);
    pthread_cond_init(&queue->not_full, NULL);
}


void queue_push(client_queue_t *queue, int client_fd, unsigned char *data) {
    pthread_mutex_lock(&queue->mutex);

    while (queue->count == QUEUE_SIZE) {
        pthread_cond_wait(&queue->not_full, &queue->mutex);
    }

    client_request_t *request = &queue->requests[queue->count];
    request->client_fd = client_fd;

    memcpy(request->data, data, PACKET_REQUEST_SIZE);

    request->priority = data[PACKET_REQUEST_PRIO_OFFSET];
    queue->count ++;
    pthread_cond_signal(&queue->not_empty);
    pthread_mutex_unlock(&queue->mutex);
}

client_request_t queue_pop(client_queue_t *queue) {
    pthread_mutex_lock(&queue->mutex);

    while (queue->count == 0) {
        pthread_cond_wait(&queue->not_empty, &queue->mutex);
    }

    int highest = 0;

    for (int i = 1; i < queue->count; i++) {
        if (queue->requests[i].priority > queue->requests[highest].priority) {
            highest = i;
        }
    }

    client_request_t request = queue->requests[highest];

    queue->requests[highest] = queue->requests[queue->count - 1];
    queue->count --;

    pthread_cond_signal(&queue->not_full);
    pthread_mutex_unlock(&queue->mutex);

    return request;
}
