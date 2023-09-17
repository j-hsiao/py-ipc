"""Define relevant errno."""
__all__ = ['EAGAIN', 'EWOULDBLOCK', 'WOULDBLOCK', 'EINTR']
import platform
try:
    import errno
except ImportError:
    EINTR = 4
    EAGAIN = 11
    EWOULDBLOCK = 10035 if platform.system() == 'Windows' else 11
else:
    EINTR = getattr(errno, 'EINTR', 4)
    EAGAIN = getattr(errno, 'EAGAIN', 11)
    EWOULDBLOCK = getattr(
        errno,
        'EWOULDBLOCK',
        10035 if platform.system() == 'Windows' else 11)

WOULDBLOCK = set([EAGAIN, EWOULDBLOCK])
