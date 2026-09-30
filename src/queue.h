#pragma once
#include "messages.h"
#include "pthread.h"
#include <string.h>
#include <stdint.h>
#include <sys/_pthread/_pthread_cond_t.h>
#include <sys/_pthread/_pthread_mutex_t.h>


#define QUEUE_SIZE 128


typedef struct {
    int client_fd;
    uint8_t priority;
    unsigned char data[PACKET_REQUEST_SIZE];
} client_request_t;


typedef struct {
    client_request_t requests[QUEUE_SIZE];

    int count;

    pthread_mutex_t mutex;
    pthread_cond_t not_empty;
    pthread_cond_t not_full;
} client_queue_t;



void queue_init(client_queue_t *queue);
void queue_push(client_queue_t *queue, int client_fd, unsigned char *data);
client_request_t queue_pop(client_queue_t *queue);
