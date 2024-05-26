"""Generic poller interface.

Resources will be wrapped in generator expressions for handling.
In general, when polling, the fewer results, the better for performance.
This is regardless of what polling mechanism is used. (poll, epoll,
select, others not yet tested.) As a result, adopt epoll one-shot like
behavior.  Objects for reading are assumed to be readable until
EWOULDBLOCK or EAGAIN or any other equivalent result.  Likewise, objects
are assumed to be writeable until EWOULDBLOCK or EAGAIN, etc.
"""
import io

class SelfFile(io.RawIOBase):
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
            c.settimeout(0)
            s.settimeout(0)
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

class Poller(object):
    """Poll resources and handle io.

    Readers are assumed to have no data available until polled
    otherwise.  Writers are assumed to be writable until polled
    otherwise.
    """
    def __init__(self, rgen, wgen):
        """Initialize a poller.

        rgen, wgen: func(poller, resource).
            These should return generators that can be stepped through
            with next().
        """
        self.control = SelfFile()
        self.running = False
        self.resources = {}
        self.rpending = {}
        self.wpending = {}
        self.rgen = rgen
        self.wgen = wgen
        self.statechanged = []

    def wrap(self, fd, resource):
        """Wrap a resource.

        Return [
            fileno: int, the file number.
            resource: the object.
            rgenerator: generator, next() should read and process a bit.
            wgenerator: generator, next() should write a bit.
            rpolling: bool, whether object should be read polled.
            wpolling: bool, whether object should be write polled.
        ]
        """
        return [
            fd, resource,
            self.rgen(self, resource), self.wgen(self, resource),
            True, False]

    def register(self, resource):
        """Add an item to poller threadsafe."""
        raise NotImplementedError
    def unregister(self, resource):
        """Remove an item from poller threadsafe."""
        raise NotImplementedError

    def add(self, resource):
        """Add a resource for handling.

        This should be called from same thread as the polling thread.
        resource: file-like object, the resource to add, should be
                  non-blocking.

        Added resources will be added to read polling only.
        When writing is required, then it will be added to self.writers
        and polled as necessary.
        """
        fd = resource.fileno()
        orig = self.resources.pop(fd, None)
        if orig is not None:
            self.remove(fd)
        wrapped = self.resources[fd] = self.wrap(fd, resource)

    def remove(self, fd):
        """Unregister from poller.

        This should be called from same thread as the polling thread.
        """
        self.rpending.pop(fd, None)
        self.wpending.pop(fd, None)
        self.resources.pop(fd, None)

    def step(self):
        """Poll registered resources and handle a little bit."""
        # result = self.poll()
        # for item in self.rpending.values():
        #     next(item)
        # for item in self.wpending.values():
        #     next(item)
        # for result in pollresult:
        #     if readable:
        #         readabit
        #         if successful:
        #             self.rpending[fd] = rgen
        #     if writable:
        #         writabit
        #         if successful:
        #             self.wpending[fd] = wgen
        # remove from any lists or whatever...
        # since cannot change dicts while iterating over them
        # for item in self.statechanged:
        #     next(item)
        raise NotImplementedError

    def run(self):
        self.running = True
        while self.running:
            self.step()

    def stop(self):
        raise NotImplementedError
