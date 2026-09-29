/**
 * @file net_io.c
 * @brief Implements blocking full-length socket read and write helpers.
 */

#include "net_io.h"

#include <errno.h>
#include <sys/socket.h>

int read_all(int fd, void *buffer, size_t length)
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

int write_all(int fd, const void *buffer, size_t length)
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
