from jhsiao.ipc.pollable import Pollable
from jhsiao.tests import simple
import select
import time

def test_pollable():
    p = Pollable()
    L = 0.1
    S = L/2
    now = time.time()
    assert not any(select.select((p,), (), (), L))
    assert time.time()-now > S
    p.set()
    now = time.time()
    assert select.select((p,), (), (), 1)[0]
    assert time.time() - now < S
    p.clear()
    now = time.time()
    assert not any(select.select((p,), (), (), 1))
    assert time.time()-now > S
    p.close()
    print('pass')

if __name__ == '__main__':
    simple(globals())
