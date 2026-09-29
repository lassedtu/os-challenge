/**
 * @file net_io.h
 * @brief Declares blocking full-length socket read and write helpers.
 */

#ifndef NET_IO_H
#define NET_IO_H

#include <stddef.h>

/**
 * @brief Reads the specified number of bytes from a file descriptor into a buffer
 * @param fd The file descriptor to read from
 * @param buffer The buffer to store the read bytes
 * @param length The number of bytes to read
 * @return 0 on success, -1 on failure
 */
int read_all(int fd, void *buffer, size_t length);

/**
 * @brief Writes the specified number of bytes from a buffer to a file descriptor
 * @param fd The file descriptor to write to
 * @param buffer The buffer containing the bytes to write
 * @param length The number of bytes to write
 * @return 0 on success, -1 on failure
 */
int write_all(int fd, const void *buffer, size_t length);

#endif
