"""Blocking local read/write pair as a single object."""
import io

class RWPair(io.RawIOBase):
    """Create a pollable object that reads/writes to fifo queue.

    Aside from write(), act like a readable only object.  This can be
    used as one of the polled objects to interrupt polling to handle
    something.
    """
    def __init__(self):
        self.r, self.w = self.fobjs()
        self.write = self.w.write
        self.read = self.r.read
        self.readinto = self.r.readinto
        self.fileno = self.r.fileno

    def fobjs(self):
        import platform
        if platform.system() == 'Windows':
            # On windows, only sockets are pollable
            import socket
            from jhsiao.ipc.sockets import sockfile
            L = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            L.bind(('127.0.0.1', 0))
            L.listen(1)
            s.connect(L.getsockname())
            c, a = L.accept()
            L.close()
            c.settimeout(None)
            s.settimeout(None)
            return sockfile.Sockfile(s, 'rb'), sockfile.Sockfile(c, 'wb')
        else:
            # On linux, pipes are pollable and some research indicates
            # they are more lightweight.
            import os, fcntl
            r, w = os.pipe()
            flag = fcntl.fcntl(r, fcntl.F_GETFL)
            fcntl.fcntl(r, fcntl.F_SETFL, flag | os.O_NONBLOCK)
            flag = fcntl.fcntl(w, fcntl.F_GETFL)
            fcntl.fcntl(w, fcntl.F_SETFL, flag | os.O_NONBLOCK)
            return os.fdopen(r, 'rb'), os.fdopen(w, 'wb')

    def fileno(self):
        self.r.fileno()
    def isatty(self):
        return False

    def readable(self):
        return True
    def read(self, amt=-1):
        return self.r.read(amt)
    def readinto(self, buf):
        return self.r.readinto(buf)

    def writable(self):
        return True
    def write(self, data):
        return self.w.write(data)
    def flush(self):
        pass

    def seekable(self):
        return False
    def seek(self, *args):
        raise io.UnsupportedOperation
    def tell(self):
        raise io.UnsupportedOperation
    def truncate(self):
        raise io.UnsupportedOperation

    def close(self):
        self.w.close()
        self.r.close()

