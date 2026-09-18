/**
 * @file protocol.c
 * @brief Implements the protocol parsing and encoding functions for the server
 */

#include "messages.h"
#include "protocol.h"

#include <string.h>

int parse_request(const unsigned char packet[PACKET_REQUEST_SIZE], struct request *request)
{
    uint64_t start_wire;
    uint64_t end_wire;

    memcpy(request->hash, packet + PACKET_REQUEST_HASH_OFFSET, sizeof(request->hash));
    memcpy(&start_wire, packet + PACKET_REQUEST_START_OFFSET, sizeof(start_wire));
    memcpy(&end_wire, packet + PACKET_REQUEST_END_OFFSET, sizeof(end_wire));

    request->start = be64toh(start_wire);
    request->end = be64toh(end_wire);
    return 0;
}

void encode_response(uint64_t answer, unsigned char packet[PACKET_RESPONSE_SIZE])
{
    uint64_t answer_wire = htobe64(answer);
    memcpy(packet + PACKET_RESPONSE_ANSWER_OFFSET, &answer_wire, sizeof(answer_wire));
}
