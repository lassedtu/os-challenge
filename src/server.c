#include <_string.h>
#include <sys/types.h>
#define LONESHA256_IMPLEMENTATION
#include "lonesha256.h"
#include "messages.h"

#include "pthread.h"
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include "cache.h"
#include "queue.h"

#define BACKLOG 128
#define WORKER_COUNT 4
#define PRIORITY_LEVELS 16

int ready_to_be_killed = 0;




typedef struct {
    client_queue_t *queue;
    cache_t *cache;
} worker_args_t;







static int recv_all(int fd, void *buffer, size_t size) {
    size_t received = 0;

    while (received < size) {
        ssize_t n = recv(fd, (char *)buffer + received, size - received, 0);

        if (n == 0) {
            return -1;
        }

        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }

            return -1;
        }

        received += n;
    }

    return 0;
}

static int send_all(int fd, const void *buffer, size_t size) {
    size_t sent = 0;

    while (sent < size) {
        ssize_t n = send(fd, (const char *)buffer + sent, size - sent, 0);

        if (n < 0) {
            if (errno == EINTR)
            {
                continue;
            }

            return -1;
        }

        sent += n;
    }

    return 0;
}

static uint64_t find_answer(const unsigned char target_hash[32], uint64_t start, uint64_t end) {
    unsigned char input[8];
    unsigned char hash[32];

    for (uint64_t number = start; number < end; number++) {
        uint64_t little_endian_number = htole64(number);
        memcpy(input, &little_endian_number, sizeof(input));

        lonesha256(hash, input, sizeof(input));

        if (memcmp(hash, target_hash, 32) == 0) {
            return number;
        }
    }

    printf("if we reach this, we are fuuuucked :(");
    return 0;
}

static void handle_client(int client_fd, unsigned char *request, cache_t *cache) {
    uint64_t answer;
    unsigned char response[PACKET_RESPONSE_SIZE];

    unsigned char *hash = request + PACKET_REQUEST_HASH_OFFSET;
    uint64_t start;
    uint64_t end;

    memcpy(&start, request + PACKET_REQUEST_START_OFFSET, sizeof(start));
    memcpy(&end, request + PACKET_REQUEST_END_OFFSET, sizeof(end));

    start = be64toh(start); // convert big-endian to native byte order :)
    end = be64toh(end);

    if (!cache_lookup(cache, hash, start, end, &answer)) {
        answer = find_answer(hash, start, end);
        cache_insert(cache, hash, start, end, answer);
    }

    // Convert answer to big-endian
    uint64_t network_answer = htobe64(answer);

    memcpy(response + PACKET_RESPONSE_ANSWER_OFFSET, &network_answer, sizeof(network_answer));
    send_all(client_fd, response, sizeof(response));

    close(client_fd);
}


static void *worker(void *arg) {
    worker_args_t *args = arg;

    while (1) {
        client_request_t request= queue_pop(args->queue);

        handle_client(request.client_fd, request.data, args->cache);
    }

    return NULL;
}

void signal_cb() {
    if (ready_to_be_killed) {
        printf("\n --> Ok, goodbye!\n");
        exit(0);
    }
    else {
        printf("\n --> Are you sure you want to quit?\n");
        ready_to_be_killed = 1;
    }
}

int main(int argc, char **argv) {
    signal(SIGINT, signal_cb);

    if (argc != 2) {
        fprintf(stderr, "usage: %s <port>\n", argv[0]);
        return EXIT_FAILURE;
    }

    int port = atoi(argv[1]);

    if (port <= 0 || port > 65535) {
        fprintf(stderr, "invalid port: %s\n", argv[1]);
        return EXIT_FAILURE;
    }

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);

    if (server_fd < 0) {
        perror("socket");
        return EXIT_FAILURE;
    }

    int reuse = 1;

    if (setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse)) < 0) {
        perror("setsockopt");
        close(server_fd);
        return EXIT_FAILURE;
    }

    struct sockaddr_in address = {.sin_family = AF_INET,
                                  .sin_addr.s_addr = htonl(INADDR_ANY),
                                  .sin_port = htons((uint16_t)port)};

    if (bind(server_fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
        perror("bind");
        close(server_fd);
        return EXIT_FAILURE;
    }

    if (listen(server_fd, BACKLOG) < 0) {
        perror("listen");
        close(server_fd);
        return EXIT_FAILURE;
    }

    printf("server listening on port %d\n", port);


    client_queue_t queue;
    cache_t cache;
    queue_init(&queue);
    cache_init(&cache);

    worker_args_t args = {
        .queue = &queue,
        .cache = &cache
    };

    pthread_t workers[WORKER_COUNT];

    for (int i = 0; i < WORKER_COUNT; i++) {
        if (pthread_create(&workers[i], NULL, worker, &args) != 0) {
            perror("pthread_create");
            return EXIT_FAILURE;
        }
    }

    while (1) {
        int client_fd = accept(server_fd, NULL, NULL);

        if (client_fd < 0) {
            if (errno == EINTR) {
                continue;
            }

            perror("accept");
            continue;
        }

        unsigned char request[PACKET_REQUEST_SIZE];

        if (recv_all(client_fd, request, sizeof(request)) != 0) {
            close(client_fd);
            continue;
        }

        queue_push(&queue, client_fd, request);
    }

    close(server_fd);
    return EXIT_SUCCESS;
}
