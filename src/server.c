/**
 * @file server.c
 * @brief Implements the main server logic, including socket setup and connection handling
 */

#define _POSIX_C_SOURCE 200809L

#include "hash_cache.h"
#include "task_queue.h"
#include "worker_pool.h"

#include <errno.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <unistd.h>

static volatile sig_atomic_t stop_requested;

/**
 * @brief Parses a string to an integer port number
 * @param text The string representation of the port number
 * @return The parsed port number on success, or -1 on failure
 */
static int parse_port(const char *text)
{
    char *end = NULL;
    long port = strtol(text, &end, 10);
    if (*text == '\0' || *end != '\0' || port < 1 || port > 65535)
    {
        return -1;
    }
    return (int)port;
}

static void request_stop(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

int main(int argc, char **argv)
{
    if (argc != 2)
    {
        fprintf(stderr, "Usage: %s port\n", argv[0]);
        return EXIT_FAILURE;
    }

    int port = parse_port(argv[1]);
    if (port < 0)
    {
        fprintf(stderr, "Invalid port: %s\n", argv[1]);
        return EXIT_FAILURE;
    }

    signal(SIGPIPE, SIG_IGN);

    // Install stop handlers without SA_RESTART so a blocking accept() returns
    // EINTR on SIGINT/SIGTERM, letting the accept loop observe stop_requested
    struct sigaction stop_action = {0};
    stop_action.sa_handler = request_stop;
    sigemptyset(&stop_action.sa_mask);
    stop_action.sa_flags = 0;
    sigaction(SIGINT, &stop_action, NULL);
    sigaction(SIGTERM, &stop_action, NULL);

    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0)
    {
        perror("socket");
        return EXIT_FAILURE;
    }

    int reuse = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

    struct sockaddr_in address = {0};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_ANY);
    address.sin_port = htons((uint16_t)port);

    if (bind(server_fd, (struct sockaddr *)&address, sizeof(address)) < 0)
    {
        perror("bind");
        close(server_fd);
        return EXIT_FAILURE;
    }
    if (listen(server_fd, SOMAXCONN) < 0)
    {
        perror("listen");
        close(server_fd);
        return EXIT_FAILURE;
    }

    hash_cache_init();
    task_queue_init();
    worker_pool_start();

    while (!stop_requested)
    {
        int client_fd = accept(server_fd, NULL, NULL);
        if (client_fd < 0)
        {
            if (errno == EINTR)
            {
                continue;
            }
            perror("accept");
            break;
        }

        struct task task;
        task.client_fd = client_fd;
        task_queue_push(task);
    }

    task_queue_shutdown();
    worker_pool_join();
    task_queue_destroy();
    hash_cache_destroy();
    close(server_fd);
    return EXIT_SUCCESS;
}
