from jhsiao.ipc.polling.poller import select, rwpair
from jhsiao.ipc.polling.gen import prelen

def test_register():
    p = select.SelectPoller(prelen.FPreLen)
    t1 = rwpair.RWPair()
    assert t1.fileno() not in p.resources
    p.register(t1)
    assert t1.fileno() not in p.resources
    p.step()
    assert t1.fileno() in p.resources
