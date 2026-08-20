#!/bin/sh
set -eu

# Standard input and output are connected to the incoming client by BusyBox nc.
# Starting the upstream connection here makes it use Gluetun's local OUTPUT path.
exec nc 10.3.0.1 5020
