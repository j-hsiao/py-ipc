import select
__all__ = ['RPoller', 'WPoller', 'RWPoller']
if hasattr(select, 'select'):
    from .select import *
if hasattr(select, 'devpoll'):
    from .devpoll import *
if hasattr(select, 'poll'):
    from .poll import *
if hasattr(select, 'epoll'):
    from .epoll import *

try:
    RPoller
except NameError:
    raise ImportError('Failed to find a polling mechanism.')
