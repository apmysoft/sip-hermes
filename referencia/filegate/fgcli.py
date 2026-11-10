#!/usr/bin/env python3
"""fgcli.py — cliente minimo de filegate para smoke tests (socket Unix)."""
import socket, sys, base64, uuid

sock_path, tokfile, op = sys.argv[1], sys.argv[2], sys.argv[3]
token = open(tokfile).read().strip()
opid = "op-" + str(uuid.uuid4())
b64 = lambda p: base64.b64encode(p.encode()).decode()
args = sys.argv[4:]

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect(sock_path)
s.settimeout(15)

def sendline(l):
    s.sendall(l.encode() + b"\n")

if op == "write":
    sendline(f"{token} {opid} write {b64(args[0])}")
    f = s.makefile("rb")
    assert f.readline().strip() == b"READY", "protocolo: sin READY"
    s.sendall(open(args[1], "rb").read())
    s.shutdown(socket.SHUT_WR)
    print(f.read().decode(), end="")
else:
    line = f"{token} {opid} {op}"
    for a in args:
        line += f" {a}" if op == "restore" else f" {b64(a)}"
    sendline(line)
    s.shutdown(socket.SHUT_WR)
    print(s.makefile("rb").read().decode(), end="")
