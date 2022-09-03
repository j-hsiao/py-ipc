from jhsiao.ipc.shmf import Shmf
if __name__ == '__main__':
    w = Shmf(size=12)
    try:
        print(w.name, w.mmap.size(), w._created)
        print(w[:])
        r = Shmf(w.name)
        try:
            print(r.name, r.mmap.size(), r._created)
            print(r[:w.size()])

            w[:] = b'hello world!'
            print(r[:w.size()])

        finally:
            r.close()
    finally:
        w.close()
    with Shmf(size=16) as f:
        print(f.name, f[:], f.size())
    print('end context')
