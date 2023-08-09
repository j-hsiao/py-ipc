"""Basic classes."""
__all__ = ['FileWrapper', 'Reader', 'Writer']

class FileWrapper(object):
    def __init__(self, f):
        self.f = f

    def detach(self):
        ret = self.f
        self.f = None
        return ret

    def close(self):
        self.f.close()

class Reader(FileWrapper):
    """Read data.

    The wrapped file-like object should ideally support `readinto1` or
    have a guarantee that `readinto()` will make at most 1 syscall.
    This means polling can be used to allow handling multiple
    connections within a single thread.
    """
    def read(self, out):
        """Read data using a single syscall.

        This method should not raise any errors.

        Input
        =====
        out: container.
            out should support the `append()` method.

        Output
        ======
        okay: bool
            Indicates whether the underlying file is still okay.
            Okay means that
            1. No errors occurred (except maybe timeouts)
            2. No eof.
        """
        raise NotImplementedError

class Writer(FileWrapper):
    """Write data."""
    def write(self, item):
        raise NotImplementedError

    def flush(self):
        pass
