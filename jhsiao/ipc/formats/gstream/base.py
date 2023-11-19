"""Base classes."""
from jhsiao.ipc import errnos
import traceback
class SwapList(object):
    def __init__(self):
        self.l = []
        self.append = self.l.append

    def __getitem__(self, idx):
        return self.l[idx]

    def __setitem(self, idx, item):
        self.l[idx] = item

    def __len__(self):
        return len(self.l)

    def swap(self):
        ret = self.l
        self.l = []
        self.append = self.l.append
        return ret

class Reader(object):
    def __init__(self, f, output, verbose=False, **kwargs):
        """Initialize a reader.

        f: the wrapped file-like object.  Should support readinto()
        output: the output container.  Should support append().
        verbose: bool, be verbose.
        kwargs: kwargs for _iter.  Different for each subclass.
        """
        self._out = output
        self._f = f
        self._verbose = verbose
        self._it = self._iter(**kwargs)
        self._buf = next(self._it)

    def _iter(self):
        """Internal iterator to handle processing.

        It should yield a buffer to read into.  send() should be
        called to pass in the amount of data read into the buffer.
        If None is yielded, that indicates EOF and reader should be
        closed.  Send() should only ever be called with non-negative
        integers.
        """
        raise NotImplementedError

    def read(self):
        """Read a little.

        None implies would block.
        Otherwise, returns the number of bytes read.
        -1 implies error or EOF
        """
        try:
            result = self._f.readinto(self._buf)
        except EnvironmentError as e:
            if e.errno in errnos.WOULDBLOCK:
                return None
            elif e.errno == errnos.EINTR:
                return 0
            else:
                return -1
        else:
            if result is not None:
                try:
                    self._buf = self._it.send(result)
                except Exception:
                    if self._verbose:
                        traceback.print_exc()
                    return -1
                return result if result else -1
            else:
                return None
