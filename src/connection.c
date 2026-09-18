/**
 * @file connection.c
 * @brief Implements the connection handling logic for the server
 */

#include "connection.h"
#include "hashing.h"
#include "messages.h"
#include "protocol.h"

#include <errno.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <unistd.h>

/**
 * @brief Reads the specified number of bytes from a file descriptor into a buffer
 * @param fd The file descriptor to read from
 * @param buffer The buffer to store the read bytes
 * @param length The number of bytes to read
 * @return 0 on success, -1 on failure
 */
static int read_all(int fd, void *buffer, size_t length)
{
    unsigned char *bytes = buffer;
    size_t received = 0;

    while (received < length)
    {
        ssize_t count = recv(fd, bytes + received, length - received, 0);
        if (count == 0)
        {
            return -1;
        }
        if (count < 0)
        {
            if (errno == EINTR)
            {
                continue;
            }
            return -1;
        }
        received += (size_t)count;
    }
    return 0;
}

/**
 * @brief Writes the specified number of bytes from a buffer to a file descriptor
 * @param fd The file descriptor to write to
 * @param buffer The buffer containing the bytes to write
 * @param length The number of bytes to write
 * @return 0 on success, -1 on failure
 */
static int write_all(int fd, const void *buffer, size_t length)
{
    const unsigned char *bytes = buffer;
    size_t sent = 0;

    while (sent < length)
    {
        ssize_t count = send(fd, bytes + sent, length - sent, 0);
        if (count < 0)
        {
            if (errno == EINTR)
            {
                continue;
            }
            return -1;
        }
        sent += (size_t)count;
    }
    return 0;
}

void *handle_connection(void *argument)
{
    int client_fd = *(int *)argument;
    free(argument);

    unsigned char request_packet[PACKET_REQUEST_SIZE];
    unsigned char response_packet[PACKET_RESPONSE_SIZE];
    struct request request;
    uint64_t answer;

    if (read_all(client_fd, request_packet, sizeof(request_packet)) == 0 &&
        parse_request(request_packet, &request) == 0)
    {
        find_hash_answer(request.hash, request.start, request.end, &answer);
        encode_response(answer, response_packet);
        write_all(client_fd, response_packet, sizeof(response_packet));
    }

    close(client_fd);
    return NULL;
}
