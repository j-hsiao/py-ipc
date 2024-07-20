import threading

from jhsiao.ipc.polling import queue

try:
    import queue as _queue
except ImportError:
    import Queue as _queue

def add(name, q, amt):
    for i in range(amt):
        q.push((name, i))

def remove(q, cmb):
    try:
        while 1:
            cmb.put(q.pop(1))
    except _queue.Empty:
        return

def test_q():
    NITHREADS = 10
    NOTHREADS = 10
    NITEMS = 100
    q = queue.Queue()
    out = _queue.Queue()
    ithreads = [
        threading.Thread(target=add, args=[i, q, NITEMS])
        for i in range(NITHREADS)]
    othreads = [
        threading.Thread(target=remove, args=[q, out])
        for i in range(NOTHREADS)]
    for ithread in ithreads:
        ithread.start()
    for othread in othreads:
        othread.start()

    for ithread in ithreads:
        ithread.join()
    for othread in othreads:
        othread.join()
    data = []
    try:
        while 1:
            data.append(out.get(False))
    except _queue.Empty:
        pass
    data.sort()
    idx = 0
    for i in range(NITHREADS):
        for j in range(NITEMS):
            if data[idx] != (i, j):
                raise ValueError('Missing data')
            idx += 1
    assert idx == len(data)
