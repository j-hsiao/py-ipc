__all__ = ['SelectPoller']

from .select import SelectPoller

import select as _select
if hasattr(_select, 'epoll'):
    from .epoll import EpollPoller
    __all__.append('EpollPoller')

# __all__ = ['RPoller', 'WPoller', 'RWPoller']
# if hasattr(select, 'select'):
#     from .select import *
# if hasattr(select, 'devpoll') or hasattr(select, 'poll'):
#     from .poll import *
# if hasattr(select, 'epoll'):
#     from .epoll import *
# 
# try:
#     RPoller
# except NameError:
#     raise ImportError('Failed to find a polling mechanism.')
