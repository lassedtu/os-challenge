/**
 * @file protocol.h
 * @brief Declares the protocol parsing and encoding functions for the server
 */

#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>

/**
 * @struct request
 * @brief Represents a request packet structure
 */
struct request
{
    // The hash to be found, represented as a 32-byte array.
    unsigned char hash[32];
    // The starting value of the range to search for the hash.
    uint64_t start;
    // The ending value of the range to search for the hash.
    uint64_t end;
};

/**
 * @brief Parses a request packet and fills the request structure
 * @param packet The input packet containing the request data
 * @param request The output structure to be filled with parsed data
 * @return 0 on success, non-zero on failure
 */
int parse_request(const unsigned char packet[49], struct request *request);

/**
 * @brief Encodes a response packet with the given answer
 * @param answer The answer to be encoded in the response packet
 * @param packet The output packet to be filled with the encoded answer
 */
void encode_response(uint64_t answer, unsigned char packet[8]);

#endif
