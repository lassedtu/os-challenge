/**
 * @file connection.h
 * @brief Declares the connection handling function for the server
 */

#ifndef CONNECTION_H
#define CONNECTION_H

/**
 * @brief Handles a client connection in a separate thread
 * @param argument Pointer to the client file descriptor (int)
 */
void *handle_connection(void *argument);

#endif
