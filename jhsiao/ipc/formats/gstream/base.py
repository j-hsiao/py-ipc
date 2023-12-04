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
        """Create a new list and return the old one."""
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
        self._verbose = verbose
        self.out = output
        self.f = f
        self.state = [f.readinto, self._iter(**kwargs)]
        self.state.append(next(self.state[1]))

    def _iter(self):
        """Internal iterator to handle processing.

        Yield buffers that need to be filled.  send() should be used
        instead of next() to send the number of bytes that were read
        into the buffer.  In the event of wouldblock, nothing should be
        sent to the iterator.  If the stream ends, 0 will be sent to the
        iterator.

        This means that the iterator should only receive positive ints
        or None.
        """
        raise NotImplementedError

    def readit(self):
        """Iterator for handling steps."""
        readinto, it, buf = self.state
        while 1:
            try:
                result = readinto(buf)
            except EnvironmentError as e:
                if e.errno in errnos.WOULDBLOCK:
                    yield None
                elif e.errno == errnos.EINTR:
                    return 0
                else:
                    return -1
            else:
                if result is None:
                    yield None
                else:
                    try:
                        buf = it.send(result)
                    except Exception:
                        if self._verbose:
                            traceback.print_exc()
                        return -1
                    yield result if result else -1

    def read(self):
        """Read a little.

        None implies would block.
        Otherwise, returns the number of bytes read.
        -1 implies error or EOF
        """
        state = self.state
        readinto, it, buf = state
        try:
            result = readinto(buf)
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
                    state[2] = it.send(result)
                except Exception:
                    if self._verbose:
                        traceback.print_exc()
                    return -1
                return result if result else -1
            else:
                return None

def tryreader(func, verbose):
    """Wrap a readinto function with try/except.

    Converts errors to -1.  EAGAIN, EWOULDBLOCK becomes None.
    EINTR is retried immediately
    """
    def tryread(buf):
        try:
            return func(buf)
        except EnvironmentError as e:
            if e.errno in errnos.WOULDBLOCK:
                return None
            elif e.errno == errnos.EINTR:
                return tryread(buf)
            else:
                if verbose:
                    traceback.print_exc()
                return -1
        except Exception:
            if verbose:
                traceback.print_exc()
            return -1
    return tryread


def readtil(readinto, view, pos, target):
    """Read into view until pos >= target.

    readinto: the readinto function.
    view: memoryview to read into
    pos: a list containing int position.  At the end of the iterator,
        the final position will be stored in pos.
    target: target position
    """
    p = pos[0]
    while p < target:
        try:
            amt = readinto(view[p:])
        except EnvironmentError as e:
            if e.errno in errnos.WOULDBLOCK:
                yield None
            elif e.errno != errnos.EINTR:
                raise
        except Exception:
            if verbose:
                traceback.print_exc()
            yield -1
            break
        else:
            if amt:
                p += amt
                yield amt
            elif amt is None:
                yield None
            else:
                yield -1
                break
    pos[0] = p

def readtilsend(readinto):
    """Read into view until pos >= target.

    readinto: the readinto function.
    view: memoryview to read into
    pos: a list containing int position.  At the end of the iterator,
        the final position will be stored in pos.
    target: target position
    """
    view, pos, target = yield None
    while 1:
        while pos < target:
            try:
                amt = readinto(view[pos:])
            except EnvironmentError as e:
                if e.errno in errnos.WOULDBLOCK:
                    yield None
                elif e.errno != errnos.EINTR:
                    raise
            except Exception:
                if verbose:
                    traceback.print_exc()
                pos = -1
                break
            else:
                if amt:
                    pos += amt
                    yield amt
                elif amt is None:
                    yield amt
                else:
                    pos = -1
                    break
        yield 0
        view, pos, target = yield pos
