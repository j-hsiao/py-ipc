from jhsiao.ipc import errnos
import traceback

def resize_or_shift(buf, view, start, stop, targetsize, factor=1):
    """Resize the buffer or shift data to the beginning.

    If the target size is greater than len(buf), then a new buffer will
    be allocated.  The new size will be targetsize * factor truncated.
    Assume each item in the stream is approximately the same size.
    Otherwise, data is shifted to the beginning of buf.

    Return buf, view, and data_end.
    """
    cursize = stop - start
    if targetsize > len(buf):
        nbuf = bytearray(int(targetsize*factor))
        nbuf[:cursize] = view[start:stop]
        return nbuf, memoryview(nbuf), cursize
    else:
        view[:cursize] = view[start:stop]
        return buf, view, cursize

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

    Yield the amount read until target is reached or EOF or error.
    If EOF or error are reached, -1 is yielded before ending.  Otherwise
    end iteration.
    """
    p = pos[0]
    while p < target:
        try:
            amt = readinto(view[p:])
        except EnvironmentError as e:
            if e.errno in errnos.WOULDBLOCK:
                yield None
            elif e.errno != errnos.EINTR:
                yield -1
        except Exception:
            if verbose:
                traceback.print_exc()
            yield -1
            return
        else:
            if amt:
                p += amt
                yield amt
            elif amt is None:
                yield None
            else:
                yield -1
                return
    pos[0] = p

def readtilsend(readinto, verbose):
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
                    if verbose:
                        traceback.print_exc()
                    yield -1
                    return
            except Exception:
                if verbose:
                    traceback.print_exc()
                yield -1
                return
            else:
                if amt:
                    pos += amt
                    yield amt
                elif amt is None:
                    yield None
                else:
                    yield -1
                    return
        yield 0
        view, pos, target = yield pos
