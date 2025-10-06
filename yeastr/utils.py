import ast, re
import weakref
import itertools
from contextlib import AbstractContextManager
from inspect import getsource, signature
from functools import wraps, partial
from sys import version_info
from os import makedirs, getpid

if version_info[:2] == (3, 8):
    try:
        import py39unparser
    except ImportError:
        import yeastr.py39unparser

try:
    import stabilize_ast_for_ci
except ImportError:
    import yeastr.stabilize_ast_for_ci


class Moon:
    """Moon.up and Moon.node do store a strong ref over the proxied object.
    This means once you called one of those, the object is alive until you
    get rid of the Moon, store temporary Moons with MoonGrabber
    """
    def __init__(self, node, parent=None, field=None, position=None):
        self._node_ref = weakref.ref(node)
        self._node = weakref.proxy(node)
        if parent:
            self._up_ref = weakref.ref(parent)
            self._up = weakref.proxy(parent)
        else:
            # self._up_ref = None
            self._up = None
        self.up_field = field
        self.position = position  # within up_field

    @property
    def node(self):
        self._node_obj = self._node.__weakref__()
        return self._node_obj

    @property
    def up(self):
        if self._up is None:
            return None
        self._up_obj = self._up.__weakref__()
        return self._up_obj

    @up.setter
    def up(self, new):
        self._up_obj = None
        if new:
            self._up_ref = weakref.ref(new)
            self._up = weakref.proxy(new)
        else:
            self._up_ref = None
            self._up = None

    def __del__(self):
        self._node_obj = None
        self._up_obj = None

    def __str__(self):
       return (
            f'<Moon({self.node.__class__.__name__} '
            f'{self.up!r}.{self.up_field}[{self.position}]'
            f')>{ast.unparse(self.node)}</>'
        )

    def recursive_repr(self):
        return f'<Moon({repr(self.node)[5:].split(" ", 1)[0]}) from [{self.position}]{self.up_field}. {self.up.recursive_repr()}>'

    def upper(self, kind):
        node = self.up
        while node and not isinstance(node.node, kind):
            node = node.up
        return node

    def replace(self, node):
        if self.position is not None:
            getattr(self.up.node, self.up_field)[self.position] = node
        else:
            setattr(self.up.node, self.up_field, node)

    def pop(self):
        assert self.position is not None, 'weird pop?'
        field = getattr(self.up.node, self.up_field)
        field.pop(self.position)

    def pop_extend(self, nodes, filternone=False):
        if self.position is None:
            raise TransformError(f'pop_extend no known position of {self} over {self.up}')
        p = self.position
        field = getattr(self.up.node, self.up_field)
        field.pop(p)
        if filternone:
            field[p:p] = efilter(lambda none: none is not None, nodes)
        else:
            field[p:p] = nodes

    def prepend(self, node):
        assert self.position is not None, 'weird prepend?'
        getattr(self.up.node, self.up_field).insert(self.position, node)

    def append(self, node):
        assert self.position is not None, 'weird append?'
        getattr(self.up.node, self.up_field).insert(self.position + 1, node)


class MoonGrabber(AbstractContextManager):
    """To automatically free memory when something goes wrong."""
    # TODO: can we customize setattr to clean everything?
    def __enter__(self):
        self.keep = []
        return self

    def __exit__(self, *a):
        self.keep = []

    reset = __exit__

    def __call__(self, *args):
        self.keep.extend(args)


# If you want a Top-Down API, look at our mLang implementation
class MoonWalking:
    """AST traversal utility BURLA (Bottom-Up Right-to-Left and Again)
    You still have a chance to analyze the tree before it is reversed.
    This one is useful bacause of how easy it is to make transformers.
    Allows for easy reparenting.
    WARN: Changes to the ast nodes are not reflected into the moonwalking
    Notes:
    - I don't like pop music/culture at all
      - If you're such a fan, tell me, why do you think he named it like so?
        I have my own theory but I'll definitly keep it for myself
    - reversed() is faster than [::-1]
    - it's so curious to see decorators are in "depth-first order"
    """
    def __init__(  # MoonWalking
        self,
        root,
        filter_cb=None,
        before_reversing_cb=None,
    ):
        if filter_cb and filter_cb.__code__.co_argcount == 2:  # bootstrap workaround
            self.tree = []
            for moon in self._iter_ast(root):
                if (newmoon := filter_cb(moon, self)):
                    self.tree.append(newmoon)
        elif filter_cb:
            self.tree = []
            for moon in self._iter_ast(root):
                if (newmoon := filter_cb(moon)):
                    self.tree.append(newmoon)
        else:
            self.tree = list(self._iter_ast(root))
        if before_reversing_cb and before_reversing_cb(self):
            return  # eg: lambda: True will not reverse the flattened tree
        self.tree = reversed(self.tree)

    # TODO: why not a staticmethod?
    def _iter_ast(self, ast_node, parent=None, field=None, position=None):
        yield (parent := Moon(ast_node, parent, field, position))
        for fieldname, field in ast.iter_fields(ast_node):
            if isinstance(field, ast.AST):
                for it in self._iter_ast(field, parent, fieldname):
                    yield it
            elif isinstance(field, list):
                for i, it in enumerate(field):
                    if isinstance(it, ast.AST):
                        for it in self._iter_ast(it, parent, fieldname, i):
                            yield it


def ast_copy(ast_node):
    if ast_node.__class__ == list:
        return [ast_copy(ast_item) for ast_item in ast_node]
    elif ast_node is None:
        return None
    _fields = ast_node._fields
    if (cls := ast_node.__class__) in (
        ast.If, ast.Assign, ast.FunctionDef, ast.For, ast.While, ast.With,
    ):
        _fields = (*_fields, 'lineno')
    return cls(**{
        field:
            ast_copy(ast_field)
            if isinstance((ast_field := getattr(ast_node, field, None)), ast.AST)
            else [ast_copy(ast_item) for ast_item in ast_field]
            if ast_field.__class__ == list else
            ast_field  # str are immutable... and this is just str or None
        for field in _fields
    })

def add_at_the_module_beginning(ast_module, ast_node):
    """adds ast_node after module docstring and future imports"""
    # TODO: Well, that's the idea of this function :D
    ast_module.body.insert(0, ast_node)


class TransformError(BaseException): ...


YMF_hygienic = 1 << 0
YMF_mLang =    1 << 1
YMF_expr =     1 << 2


# You must always use @def_macro() when not using the BuildTimeTransformer
def def_macro(*args, hygienic=False, mLang=False, expr=False, **kwargs):
    def _def_macro(fn):
        nonlocal args
        fn.name = fn.__name__
        flags = 0
        if hygienic:
            flags |= YMF_hygienic
        if mLang:
            flags |= YMF_mLang
        if expr:
            flags |= YMF_expr
        _macros.add(fn, flags, args, kwargs)
        return fn
    return _def_macro


def mLang_conv(_ast):
    if isinstance(_ast, ast.Constant):
        return _ast.value
    elif (
        isinstance(_ast, ast.UnaryOp)
        and isinstance(_ast.op, ast.USub)
    ):
        return - mLang_conv(_ast.operand)
    elif isinstance(_ast, (ast.List, ast.Tuple)):
        return [mLang_conv(el) for el in _ast.elts]
    raise NotImplementedError(f'convert {ast.dump(_ast)}')


restricted_builtins = {
    k: v for k, v in __builtins__.items()
    if not k.startswith('_') and k not in (
        'credits', 'help', 'license', 'copyright', 'exit',
        'open', 'quit', 'compile', 'eval', 'exec'
    )
}

