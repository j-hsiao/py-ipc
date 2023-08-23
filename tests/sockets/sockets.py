from __future__ import print_function

from jhsiao.ipc.sockets import sockets, ip

def test_inet():
    L = sockets.bind_inet()
    assert L is not None
    try:
        L.listen(1)
        print(L.getsockname())
        c = sockets.connect_inet(L.getsockname())
        assert c is not None
        try:
            s, a = L.accept()
            assert s is not None
            try:
                assert s.recv(c.send(b'hello world')) == b'hello world'
            finally:
                s.close()
        finally:
            c.close()
    finally:
        L.close()

if hasattr(sockets, 'bind_unix'):
    def test_unix():
        L = sockets.bind_unix()
        assert L is not None
        try:
            L.listen(1)
            print(repr(L.getsockname()))
            c = sockets.connect_unix(L.getsockname())
            assert c is not None
            try:
                s, a = L.accept()
                assert s is not None
                try:
                    assert s.recv(c.send(b'hello world')) == b'hello world'
                finally:
                    s.close()
            finally:
                c.close()
        finally:
            L.close()

def test_generic_bind():
    L = sockets.bind()
    assert L is not None
    try:
        L.listen(1)
        print(L.family, L.type, L.getsockname())
        c = sockets.connect(L.getsockname())
        assert c is not None
        try:
            s, a = L.accept()
            try:
                assert s.recv(c.send(b'hello')) == b'hello'
            finally:
                s.close()
        finally:
            c.close()
    finally:
        L.close()

def test_ip():
    print('inet ips')
    for k, v in ip.get_ip('inet').items():
        print(repr(k))
        for addr in v:
            print('   ', addr)

    print('inet6 ips')
    for k, v in ip.get_ip('inet6').items():
        print(repr(k))
        for addr in v:
            print('   ', addr)
