# OS Challenge

This version of the project contains the initial implementation and setup of environment for the os challenge (Lasses version).

The idea is that each group member sepperately makes something that works and we then later combine together what works best for us individually into a "frankenstein" server with the best from each implementations.

## How to run on Apple Silicon

VMware Fusion and Vagrant should be installed and set up.

From the repository root:

```sh
cd arm64
vagrant up server
vagrant up client
```

In one terminal start the server:

```sh
vagrant ssh server
cd os-challenge-common
make
./server 5003
```

In another terminal run the client:

```sh
cd arm64
vagrant ssh client
cd os-challenge-common
./run-client.sh
```

Build the server inside the Linux VM. A macOS binary will not run on Linux.

## Notes on current version

For now the server uses a linear reverse-hashing function. It checks each number in the request range in order. It also uses a simple byte comparison for hashes.

This was hacked together from different code snippets i wrote while planning for the project. This code was added rewritten to make something that works from the start and to test the server + the rest of the environment, not to make something that is acceptable to turn in.

In fact the entire codebase of this version has been hacked together from different tests and code snippets written while preparing for the project, with added proper documentation and some improvements.

The focus of this version of the code is simply to get a server up and running and a dev environment that can cleanly build (make / make clean) as well as properly documenting and splitting up code to relevant files.

## Extra notes

The server must be at the root folder as specified in the os challenge doc, however the build artifacts / object files are put into the /build folder.

The src folder contains all the code associated with the project.