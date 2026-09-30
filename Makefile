CC = gcc
CFLAGS = -Wall -Wextra -O3 -pthread


server: src/server.c src/queue.c src/cache.c src/queue.h src/cache.h src/lonesha256.h src/messages.h
	$(CC) $(CFLAGS) src/server.c src/cache.c src/queue.c -o server

run: server
	./server 5003

clean:
	rm -f server
