"""Local bounded JSON request/response transport."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import socketserver
from threading import BoundedSemaphore, Thread

MAX_REQUEST = 8192
MAX_REPLY = 524288
DEFAULT_SOCKET = "/run/rc-printstation/station.sock"


class StationServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads=True
    block_on_close=False
    request_queue_size=8

    def __init__(self,path,core):
        self.core=core
        self.limit=BoundedSemaphore(8)
        self.path=Path(path)
        if self.path.is_socket():
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as probe:
                probe.settimeout(.2)
                try:
                    probe.connect(str(path))
                except ConnectionRefusedError:
                    self.path.unlink()
                else:
                    raise RuntimeError("Station socket already active")
        previous=os.umask(0o077)
        try:
            super().__init__(str(path),Handler)
        finally:
            os.umask(previous)

    def process_request(self,request,address):
        if not self.limit.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request,address)

    def process_request_thread(self,request,address):
        try:
            super().process_request_thread(request,address)
        finally:
            self.limit.release()

    def handle_error(self,request,address):
        # Request bodies and local credentials never enter stderr.
        pass

    def server_close(self):
        super().server_close()
        if self.path.is_socket():
            self.path.unlink()


class Handler(socketserver.StreamRequestHandler):
    timeout=.7

    def handle(self):
        raw=self.rfile.readline(MAX_REQUEST+1)
        if len(raw)>MAX_REQUEST or not raw.endswith(b"\n"):
            return
        try:
            request=json.loads(raw)
            if isinstance(request,dict):
                source=request.pop("client","local")
            else:
                source="local"
            if not isinstance(source,str) or len(source)>64:
                return
            data=self.server.core.command(request,source)
        except (ValueError,RecursionError):
            data={"ok":False,"error":"Ungültige Eingabe."}
        answer=json.dumps(data,ensure_ascii=False,separators=(",",":")).encode()+b"\n"
        if len(answer)<=MAX_REPLY:
            self.wfile.write(answer)


@contextmanager
def serving(path,core):
    server=StationServer(path,core)
    thread=Thread(target=server.serve_forever,kwargs={"poll_interval":.2},daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def request(path,message,timeout=.8):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(os.fspath(path))
        client.sendall(json.dumps(message,ensure_ascii=False,separators=(",",":")).encode()+b"\n")
        with client.makefile("rb") as reply:
            raw=reply.readline(MAX_REPLY+1)
            if not raw.endswith(b"\n") or len(raw)>MAX_REPLY:
                raise OSError("Invalid station response")
            return json.loads(raw)
