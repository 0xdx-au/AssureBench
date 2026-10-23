#!/usr/local/bin/python3
import os
import stat
import sys

docker_socket = "/var/run/docker.sock"
try:
    socket_gid = os.stat(docker_socket).st_gid
    if not stat.S_ISSOCK(os.stat(docker_socket).st_mode):
        raise RuntimeError(f"{docker_socket} is not a Unix socket")
except OSError as error:
    raise SystemExit(f"AssureBench requires the Docker socket at {docker_socket}: {error}")

try:
    os.setgroups(sorted({0, socket_gid}))
    os.setgid(0)
    os.setuid(10001)
except OSError as error:
    raise SystemExit(f"AssureBench could not drop privileges: {error}")

if len(sys.argv) < 2:
    raise SystemExit("AssureBench entrypoint needs a command")
os.execvp(sys.argv[1], sys.argv[1:])
