"""Yeastr internal utils"""
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
    """Yeastr's fundamental building block.

    Basically holds weakref to ast.AST with position and metadata.

    When you get node or up, the weakref is converted to a trong ref.

    This means once you called one of those properties,
    the object is alive until you get rid of the Moon.

    Store temporary Moons with :class:`MoonGrabber`

    Moon has helpers to edit the ast-tree in-place.

    """
    def __init__(self, node, parent=None, field=None, position=None):
        # TypeError: cannot create weak reference to 'list' object
        # here probably means you are building a bad tree
        if isinstance(node, str):
            self._node_ref = lambda: node
        else:
            self._node_ref = weakref.ref(node)
        if parent:
            self._up_ref = weakref.ref(parent)
        else:
            self._up_ref = None
        self.up_field = field
        self.position = position  # within up_field

    @property
    def node(self):
        """``ast.AST`` Corresponding to this moon"""
        self._node_obj = self._node_ref()
        return self._node_obj

    @property
    def up(self):
        """``ast.AST`` Corresponding to this moon's parent"""
        if self._up_ref is None:
            return None
        self._up_obj = self._up_ref()
        return self._up_obj

    @up.setter
    def up(self, new):
        """Change the parent (doesn't edit the tree)

        :param new: The new parent
        :type new: Moon
        """
        self._up_obj = None
        if new:
            self._up_ref = weakref.ref(new)
        else:
            self._up_ref = None

    def __str__(self):
       return (
            f'<Moon({self.node.__class__.__name__} '
            f'{self.up!r}.{self.up_field}[{self.position}]'
            f')>{ast.unparse(self.node) if not isinstance(self.node, str) else self.node}</>'
        )

    def recursive_repr(self):
        return f'<Moon({repr(self.node)[5:].split(" ", 1)[0]}) from [{self.position}]{self.up_field}. {self.up.recursive_repr()}>'

    def upper(self, kind):
        """Find the closest upper Moon matching the kind provided

        :param kind: search term
        :type kind: ast.AST | Tuple[ast.AST]
        :rtype: Moon | None"""
        node = self.up
        while node and not isinstance(node.node, kind):
            node = node.up
        return node

    def replace(self, node):
        """Edits the ast.AST, in-place replacing moon.node with node"""
        if self.position is not None:
            getattr(self.up.node, self.up_field)[self.position] = node
        else:
            setattr(self.up.node, self.up_field, node)

    def replace_str(self, new_str):
        setattr(self.up.node, self.up_field, new_str)

    def pop(self):
        """Edits the ast.AST, in-place removing moon.node"""
        assert self.position is not None, 'weird pop?'
        field = getattr(self.up.node, self.up_field)
        field.pop(self.position)

    def pop_extend(self, nodes, filternone=False):
        """Edits the ast.AST, in-place removing moon.node and adding nodes

        :param nodes: nodes to be added
        :type nodes: Iterable[ast.AST | None]

        :param filternone: Strip None, defaults to raise
        :type filternone: bool
        """
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
        """Edits the ast.AST, in-place adding node before moon.node"""
        assert self.position is not None, 'weird prepend?'
        getattr(self.up.node, self.up_field).insert(self.position, node)

    def append(self, node):
        """Edits the ast.AST, in-place adding node after moon.node"""
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

    The tree is flattened, then reversed

    You still have a chance to analyze the tree before it is reversed.

    This one is useful bacause of how easy it is to make transformers.

    Allows for easy reparenting.

    .. warning::
        Changes to the ast nodes are not reflected into the moonwalking

    .. note:: I don't like pop music/culture at all
        If you're such a fan, tell me, why do you think he named it like so?

        I have my own theory but I'll definitly keep it for myself

    .. tip:: (implementation choice) A reverse_iterator is faster than the eager [::-1]
        So if you want to edit the tree, it must be done in the callbacks

    .. note:: It's so curious to see decorators are in "depth-first order"
    """
    def __init__(  # MoonWalking
        self,
        root,
        filter_cb=None,
        before_reversing_cb=None,
    ):
        """Creates the tree of :class:`Moon`s and almost reverses it.

        :param root: The node to start analyzing from
        :type root: ast.AST

        :param filter_cb: A 1 argument callback gets the moon, and returns it to store the moon in the tree.

            Optional 2nd argument is the MoonWalking itself, so you can add more moons to the tree.

            Defaults to store every moon.
        :type filter_cb: Callable[[Moon], Moon] | Callable[[Moon, MoonWalking], Moon]

        :param before_reversing_cb: Callback called before the tree gets reversed.

            If the callback returns True, the tree won't be reversed
        :type before_reversing_cb: Callable[[MoonWalking], bool]
        """
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

    @staticmethod
    def _iter_ast(ast_node, parent=None, field=None, position=None):
        """Generator called by __init__, yields Moons.

        field values:
        - list yielded unpacked
        - str are yielded;
        - numbers and None are not yielded
        """
        yield (parent := Moon(ast_node, parent, field, position))
        for fieldname, _field in ast.iter_fields(ast_node):
            if isinstance(_field, ast.AST):
                for it in MoonWalking._iter_ast(_field, parent, fieldname):
                    yield it
            elif isinstance(_field, list):
                for i, it in enumerate(_field):
                    if isinstance(it, ast.AST):
                        for it in MoonWalking._iter_ast(it, parent, fieldname, i):
                            yield it
            elif isinstance(_field, str):
                yield Moon(_field, parent, fieldname)


def ast_copy(ast_node):
    """deepcopy of :class:`ast.AST` tree, just faster"""
    if ast_node.__class__ == list:
        return [ast_copy(ast_item) for ast_item in ast_node]
    elif ast_node.__class__ == str:  # ast.Nonlocal/ast.Global
        return ast_node
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


# TODO: MOVE THESE two out of here!!
@def_macro
def module_future_imports_count(ast_module, yr_counter):
    counter = 1 if yam_module_docstring(ast_module) else 0
    while yam_future_import(ast_module.body[counter]):
        counter += 1

def add_at_the_module_beginning(ast_module, ast_node):
    """Adds ast_node after module docstring and future imports"""
    module_future_imports_count(ast_module, position)
    ast_module.body.insert(position, ast_node)


def strip_module_docstring(ast_module):
    assert ast_module.__class__ == ast.Module
    if (
        (ex := ast_module.body[0]).__class__ == ast.Expr
        and ex.value.__class__ == ast.Constant
        and ex.value.value.__class__ == str
    ):
        return ast_module.body.pop(0)


class TransformError(BaseException): ...


YMF_hygienic = 1 << 0
YMF_mLang    = 1 << 1
YMF_expr     = 1 << 2
YMF_XMacro   = 1 << 3
YMF_YMacro   = 1 << 4
YMF_ZMacro   = 1 << 5


# You must always use @def_macro() when not using the BuildTimeTransformer
def def_macro(
    *args,
    hygienic=False,
    mLang=False,
    expr=False,
    XMacro=False,
    YMacro=False,
    ZMacro=False,
    **kwargs
):
    """@def_macro() decorator for JIT macros only"""
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
        if XMacro:
            flags |= YMF_XMacro
        if YMacro:
            flags |= YMF_YMacro
        if ZMacro:
            flags |= YMF_ZMacro
        _macros.add(fn, flags, args, kwargs)
        return fn
    return _def_macro


def mLang_conv(_ast):
    """macro parameters conversion step for mLang"""
    # TODO: isn't just literal_eval but more limited?
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

