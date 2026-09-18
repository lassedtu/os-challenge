/**
 * @file server.c
 * @brief Implements the main server logic, including socket setup and connection handling
 */

#define _POSIX_C_SOURCE 200809L

#include "connection.h"

#include <errno.h>
#include <netinet/in.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <unistd.h>

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

    for (;;)
    {
        int client_fd = accept(server_fd, NULL, NULL);
        if (client_fd < 0)
        {
            if (errno == EINTR)
            {
                continue;
            }
            perror("accept");
            close(server_fd);
            return EXIT_FAILURE;
        }

        int *client_fd_copy = malloc(sizeof(*client_fd_copy));
        if (client_fd_copy == NULL)
        {
            close(client_fd);
            continue;
        }
        *client_fd_copy = client_fd;

        pthread_t thread;
        int result = pthread_create(&thread, NULL, handle_connection, client_fd_copy);
        if (result != 0)
        {
            free(client_fd_copy);
            close(client_fd);
            continue;
        }
        pthread_detach(thread);
    }
}
