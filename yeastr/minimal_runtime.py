from collections.abc import Sequence
from collections import deque
from array import array
from collections.abc import Mapping
from types import MappingProxyType
try:
    from random import randbytes
except ImportError:
    from secrets import token_bytes as randbytes


def ymatch_as_seq(obj):
    # PEP634 - Sequence Patterns, properly explains this check
    if obj.__class__.__flags__ & 32:  # for bootstrapped
        return True  # speed up detection on py3.10+
    return isinstance(obj, (Sequence, array, deque))\
        and not isinstance(obj, (str, bytes, bytearray))

def ymatch_as_map(obj):
    if obj.__class__.__flags__ & 64:  # for bootstrapped
        return True  # speed up detection on py3.10+
    return isinstance(obj, (Mapping, dict, MappingProxyType))

def ymatch_positional_origin(obj):
    if hasattr(obj, '__dataclass_fields__'):
        return list(obj.__dataclass_fields__.keys())
    if hasattr(obj, '__match_args__'):
        return obj.__match_args__


def random_string(length):
    return ''.join([f"{x:0x}" for x in randbytes(length // 2)])

# functional helpers, just to try things on the repl
# with_call2comp will transform them into comprehensions
# so these function definitions are kinda stub
# these do not enforce what the transformer can actually do
# so these are more compatible, but should be slower
# If the transormer can't transform,
# then the user can choose to fallback into calling one the these
def emap(fn, _iter):
    if fn.__code__.co_argcount == 1:
        return [*map(fn, _iter)]
    return [*map(lambda a: fn(*a), _iter)]
emapl = emap

def emaps(fn, _iter):
    if fn.__code__.co_argcount == 1:
        return set(map(fn, _iter))
    return set(map(lambda a: fn(*a), _iter))

def emapd(fn, _iter):
    if fn.__code__.co_argcount == 1:
        return dict(map(fn, __iter))
    return dict(map(lambda a: fn(*a), _iter))

def efilter(fn, _iter):
    if fn.__code__.co_argcount == 1:
        return [*filter(fn, _iter)]
    return [*filter(lambda a: fn(*a), _iter)]
efilterl = efilter

def efilters(fn, _iter):
    if fn.__code__.co_argcount == 1:
        return set(filter(fn, _iter))
    return set(filter(lambda a: fn(*a), _iter))

def efilterd(fn, _iter):
    if fn.__code__.co_argcount == 1:
        return dict(filter(fn, _iter))
    return dict(filter(lambda a: fn(*a), _iter))

def efiltermap(_fil, _map, _iter):
    return [*map(_map, filter(_fil, _iter))]
efiltermapl = efiltermap

def efiltermaps(_fil, _map, _iter):
    return set(map(_map, filter(_fil, _iter)))

def efiltermapd(_fil, _map, _iter):
    if _fil.__code__.co_argcount != _map.__code__.co_argcount:
        raise TypeError('efiltermapd: arity mismatch')
    if _fil.__code__.co_argcount == 1:
        return dict(map(_map, filter(_fil, _iter)))
    return dict(*map(lambda args: _map(*args),
                     filter(lambda args: _fil(*args), _iter)))

