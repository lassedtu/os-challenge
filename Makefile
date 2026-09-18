CC ?= gcc
CFLAGS ?= -O3 -Wall -Wextra -Wpedantic
CPPFLAGS ?= -D_DEFAULT_SOURCE
LDFLAGS ?=
LDLIBS ?= -pthread

.PHONY: all clean

SOURCES := $(wildcard src/*.c)
OBJECTS := $(patsubst src/%.c,build/%.o,$(SOURCES))

all: server

server: $(OBJECTS)
	$(CC) $(LDFLAGS) -o $@ $(OBJECTS) $(LDLIBS)

build/%.o: src/%.c
	mkdir -p build
	$(CC) $(CPPFLAGS) $(CFLAGS) -Isrc -c $< -o $@

clean:
	rm -rf build server