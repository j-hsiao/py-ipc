"""Generic poller interface.

Resources will be wrapped in generator expressions for handling.
In general, when polling, the fewer results, the better for performance.
This is regardless of what polling mechanism is used. (poll, epoll,
select, others not yet tested.) As a result, adopt epoll one-shot like
behavior.  Objects for reading are assumed to be readable until
EWOULDBLOCK or EAGAIN or any other equivalent result.
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

# TODO:
# change linked list to dict may traverse multiple times
# so insert/deletion times are probably less significant...
# plus, dict interface is easier to handle
ITEM = 0
RPRE = 1
RPST = 2
WPRE = 3
WPST = 4
RGEN = 5
WGEN = 6
class Poller(object):
    """Poll resources and handle io.

    Readers are assumed to have no data available until polled
    otherwise.  Writers are assumed to be writable until polled
    otherwise.
    """
    def __init__(self):
        """Initialize a poller."""
        self.running = False
        self.resources = {}
        self.writers = None
        self.readers = None

    def wrap(self, resource):
        """Wrap a resource.

        For constant time addition/removal from list of readers/writers
        to handle, objects are stored as doubly linked list.
        [object, rpre, rpost, wpre, wpost, ...] where ... is determined
        by subclasses.
        """
        return [resource, None, None, None, None]

    def add(self, resource):
        """Add a resource for handling.

        resource: file-like object, the resource to add, should be
                  non-blocking.

        Added resources will be added to read polling only.
        When writing is required, then it will be added to self.writers
        and polled as necessary.
        """
        fd = resource.fileno()
        orig = self.resources.pop(resource.fileno(), None)
        if orig is not None:
            self.rremove(orig)
            self.wremove(orig)
        self.resources[fd] = self.wrap(resource)

    def radd(self, item):
        """Add an item to read handling, assume not already added."""
        item[RPST] = self.readers
        item[RPRE] = None
        if self.readers is not None:
            self.readers[RPRE] = item
        self.readers = item
    def wadd(self, item):
        """Add an item to write handling, assume not already added."""
        item[WPST] = self.writers
        item[WPRE] = None
        if self.writers is not None:
            self.writers[WPRE] = item
        self.writers = item

    def rrem(self, item):
        """Remove an item from read handling."""
        if item[RPRE] is None:
            self.readers = item[RPST]
        else:
            item[RPRE][RPST] = item[RPST]
            item[RPST][RPRE] = item[RPRE]
    def wrem(self, item):
        """Remove an item from write handling."""
        if item[WPRE] is None:
            self.writers = item[WPST]
        else:
            item[WPRE][WPST] = item[WPST]
            item[WPST][WPRE] = item[WPRE]

    def step(self):
        """Poll registered resources and handle a little bit."""
        raise NotImplementedError

        ritem = self.readers
        witem = self.writers
        # do polling
        # do a step and if more, add to readers/writers
        # ritem/witem keep ref to start of original readers/writers
        # so fair handling.
        while ritem is not None:
            nitem = ritem[RPST]
            next(ritem[RGEN])
            ritem = nitem
        while witem is not None:
            nitem = witem[WPST]
            next(witem[WGEN])
            witem = nitem



    def run(self):
        self.running = True
        while self.running:
            self.step()
