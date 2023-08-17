from __future__ import print_function
import io
import functools
import socket
import sys
import time
import platform

from jhsiao.ipc import polling
from jhsiao.ipc.sockets.formats import bases

def connect_polling(pollercls):
    """Test polling on connect to listening socket."""
    poller = pollercls()
    L = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    L.bind(('localhost', 0))
    L.listen(1)
    # no data
    try:
        poller.register(L, poller.r)
        now = time.time()
        assert list(poller.poll(.1)) == [[], [], []]
        assert time.time() - now > .05
        now = time.time()
        assert list(poller.anypoll(.1)) == []
        assert time.time() - now > .05

        # has data
        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.connect(('localhost', L.getsockname()[1]))
        try:
            now = time.time()
            assert list(poller.poll(.1)) == [[L], [], []]
            assert time.time() - now < .05
            now = time.time()
            assert list(poller.anypoll(.1)) == [L]
            assert time.time() - now < .05
        finally:
            s, a = L.accept()
            s.close()
            c.close()

        # oneshot, nodata
        poller[L] = poller.r | poller.o
        now = time.time()
        assert list(poller.poll(.1)) == [[], [], []]
        assert time.time() - now > .05
        now = time.time()
        assert list(poller.anypoll(.1)) == []
        assert time.time() - now > .05

        # Select poller without any registered items will
        # result in instant return on windows
        # and generally, windows only supports select.
        if platform.system() == 'Windows':
            EMPTY = 0
        else:
            EMPTY = .05
        # oneshot, has data
        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.connect(('localhost', L.getsockname()[1]))
        try:
            now = time.time()
            assert list(poller.poll(.1)) == [[L], [], []]
            assert time.time() - now < .05
            now = time.time()
            assert list(poller.poll(.1)) == [[], [], []]
            assert time.time() - now >= EMPTY
            poller.register(L, 'ro')
            now = time.time()
            assert list(poller.poll(.1)) == [[L], [], []]
            assert time.time() - now < .05
            now = time.time()
            assert list(poller.poll(.1)) == [[], [], []]
            assert time.time() - now >= EMPTY
        finally:
            s, a = L.accept()
            s.close()
            c.close()

        poller[L] = 'ro'
        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c.connect(('localhost', L.getsockname()[1]))
        try:
            now = time.time()
            assert list(poller.anypoll(.1)) == [L]
            assert time.time() - now < .05
            now = time.time()
            assert list(poller.anypoll(.1)) == []
            assert time.time() - now >= EMPTY
            poller[L] = poller.r | poller.o
            now = time.time()
            assert list(poller.anypoll(.1)) == [L]
            assert time.time() - now < .05
            now = time.time()
            assert list(poller.anypoll(.1)) == []
            assert time.time() - now >= EMPTY
        finally:
            s, a = L.accept()
            s.close()
            c.close()
    finally:
        L.close()


def clear_socket(s, buf):
    """Clear out pending data from a socket (read until would block).

    Expect s to be non-blocking.
    """
    total = 0
    try:
        amt = s.recv_into(buf)
        while amt:
            total += amt
            amt = s.recv_into(buf)
    except EnvironmentError as e:
        if e.errno not in bases.WOULDBLOCK:
            raise
    return total

def fill_socket(s, buf):
    total = 0
    try:
        while 1:
            total += s.send(buf)
    except EnvironmentError as e:
        if e.errno not in bases.WOULDBLOCK:
            raise
    return total


def recv_polling(pollercls):
    """Test polling on receiving data."""
    poller = pollercls()
    L = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    L.bind(('localhost', 0))
    L.listen(1)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(L.getsockname())
    c, a = L.accept()

    # no data
    try:
        poller.register(s, poller.r)
        now = time.time()
        assert list(poller.poll(.1)) == [[], [], []]
        assert time.time() - now > .05
        now = time.time()
        assert list(poller.anypoll(.1)) == []
        assert time.time() - now > .05

        # has data
        c.send(b'1')
        now = time.time()
        assert list(poller.poll(.1)) == [[s], [], []]
        assert time.time() - now < .05
        now = time.time()
        assert list(poller.anypoll(.1)) == [s]
        assert time.time() - now < .05
        s.recv(1)

        # oneshot, nodata
        poller[s] = poller.r | poller.o
        now = time.time()
        assert list(poller.poll(.1)) == [[], [], []]
        assert time.time() - now > .05
        now = time.time()
        assert list(poller.anypoll(.1)) == []
        assert time.time() - now > .05

        # Select poller without any registered items will
        # result in instant return on windows
        # and generally, windows only supports select.
        if platform.system() == 'Windows':
            EMPTY = 0
        else:
            EMPTY = .05
        # oneshot, has data
        c.send(b'1')
        now = time.time()
        assert list(poller.poll(.1)) == [[s], [], []]
        assert time.time() - now < .05
        now = time.time()
        assert list(poller.poll(.1)) == [[], [], []]
        assert time.time() - now >= EMPTY
        poller.register(s, 'ro')
        now = time.time()
        assert list(poller.poll(.1)) == [[s], [], []]
        assert time.time() - now < .05
        now = time.time()
        assert list(poller.poll(.1)) == [[], [], []]
        assert time.time() - now >= EMPTY
        s.recv(1)

        poller[s] = 'ro'
        c.send(b'1')
        now = time.time()
        assert list(poller.anypoll(.1)) == [s]
        assert time.time() - now < .05
        now = time.time()
        assert list(poller.anypoll(.1)) == []
        assert time.time() - now >= EMPTY
        poller[s] = poller.r | poller.o
        now = time.time()
        assert list(poller.anypoll(.1)) == [s]
        assert time.time() - now < .05
        now = time.time()
        assert list(poller.anypoll(.1)) == []
        assert time.time() - now >= EMPTY
        s.recv(1)
    finally:
        L.close()
        c.close()
        s.close()

def send_polling(pollercls):
    L = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    L.bind(('localhost', 0))
    L.listen(1)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(L.getsockname())
    c, a = L.accept()
    s.settimeout(0)
    c.settimeout(0)

    buf = bytearray(8192)

    poller = pollercls()
    try:
        # can write
        poller.register(s, poller.w)
        now = time.time()
        assert list(poller.poll(.1)) == [[], [s], []]
        assert time.time() - now < .05
        now = time.time()
        assert list(poller.anypoll(.1)) == [s]
        assert time.time() - now < .05

        # full
        print('filled with', fill_socket(s, buf), 'bytes')
        now = time.time()
        assert list(poller.poll(.1)) == [[], [], []]
        assert time.time() - now > .05
        now = time.time()
        assert list(poller.anypoll(.1)) == []
        assert time.time() - now > .05

        # oneshot, full
        poller[s] = poller.w | poller.o
        now = time.time()
        assert list(poller.poll(.1)) == [[], [], []]
        assert time.time() - now > .05
        now = time.time()
        assert list(poller.anypoll(.1)) == []
        assert time.time() - now > .05

        print('cleared', clear_socket(c, buf), 'bytes')
        if platform.system() == 'Windows':
            EMPTY = 0
        else:
            EMPTY = .05

        # oneshot, canwrite
        now = time.time()
        assert list(poller.poll(.1)) == [[], [s], []]
        assert time.time() - now < .05
        now = time.time()
        assert list(poller.poll(.1)) == [[], [], []]
        assert time.time() - now >= EMPTY
        poller.register(s, 'wo')
        now = time.time()
        assert list(poller.poll(.1)) == [[], [s], []]
        assert time.time() - now < .05
        now = time.time()
        assert list(poller.poll(.1)) == [[], [], []]
        assert time.time() - now >= EMPTY


        poller[s] = 'wo'
        assert list(poller.anypoll(.1)) == [s]
        assert time.time() - now < .05
        now = time.time()
        assert list(poller.anypoll(.1)) == []
        assert time.time() - now >= EMPTY
        poller.register(s, 'wo')
        now = time.time()
        assert list(poller.anypoll(.1)) == [s]
        assert time.time() - now < .05
        now = time.time()
        assert list(poller.anypoll(.1)) == []
        assert time.time() - now >= EMPTY

    finally:
        s.close()
        c.close()
        L.close()



try:
    test_select_connect = functools.partial(
        connect_polling, polling.SelectPoller)
    test_select_recv = functools.partial(
        recv_polling, polling.SelectPoller)
    test_select_send = functools.partial(
        send_polling, polling.SelectPoller)
except AttributeError:
    pass
try:
    test_devpoll_connect = functools.partial(
        connect_polling, polling.DevpollPoller)
    test_devpoll_recv = functools.partial(
        recv_polling, polling.DevpollPoller)
    test_devpoll_send = functools.partial(
        send_polling, polling.DevpollPoller)
except AttributeError:
    pass
try:
    test_poll_connect = functools.partial(
        connect_polling, polling.PollPoller)
    test_poll_recv = functools.partial(
        recv_polling, polling.PollPoller)
    test_poll_send = functools.partial(
        send_polling, polling.PollPoller)
except AttributeError:
    pass
try:
    test_epoll_connect = functools.partial(
        connect_polling, polling.EpollPoller)
    test_epoll_recv = functools.partial(
        recv_polling, polling.EpollPoller)
    test_epoll_send = functools.partial(
        send_polling, polling.EpollPoller)
except AttributeError:
    pass
