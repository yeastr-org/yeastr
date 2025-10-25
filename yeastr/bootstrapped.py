# Getting macros from yeastr/shared.ypy
# Getting macros from yeastr/yam.ypy
# Amalgamating from yeastr/utils.py
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
        if isinstance(node, str):
            self._node_ref = lambda: node
        else:
            self._node_ref = weakref.ref(node)
        if parent:
            self._up_ref = weakref.ref(parent)
        else:
            self._up_ref = None
        self.up_field = field
        self.position = position

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
        return f'<Moon({self.node.__class__.__name__} {self.up!r}.{self.up_field}[{self.position}])>{(ast.unparse(self.node) if not isinstance(self.node, str) else self.node)}</>'

    def recursive_repr(self):
        return f"<Moon({repr(self.node)[5:].split(' ', 1)[0]}) from [{self.position}]{self.up_field}. {self.up.recursive_repr()}>"

    def upper(self, kind):
        """Find the closest upper Moon matching the kind provided

        :param kind: search term
        :type kind: ast.AST | Tuple[ast.AST]
        :rtype: Moon | None"""
        node = self.up
        while node and (not isinstance(node.node, kind)):
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
            field[p:p] = [none for none in nodes if none is not None]
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

    def __enter__(self):
        self.keep = []
        return self

    def __exit__(self, *a):
        self.keep = []
    reset = __exit__

    def __call__(self, *args):
        self.keep.extend(args)

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

    def __init__(self, root, filter_cb=None, before_reversing_cb=None):
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
        if filter_cb and filter_cb.__code__.co_argcount == 2:
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
            return
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
        for (fieldname, _field) in ast.iter_fields(ast_node):
            if isinstance(_field, ast.AST):
                for it in MoonWalking._iter_ast(_field, parent, fieldname):
                    yield it
            elif isinstance(_field, list):
                for (i, it) in enumerate(_field):
                    if isinstance(it, ast.AST):
                        for it in MoonWalking._iter_ast(it, parent, fieldname, i):
                            yield it
            elif isinstance(_field, str):
                yield Moon(_field, parent, fieldname)

def ast_copy(ast_node):
    """deepcopy of :class:`ast.AST` tree, just faster"""
    if ast_node.__class__ == list:
        return [ast_copy(ast_item) for ast_item in ast_node]
    elif ast_node.__class__ == str:
        return ast_node
    elif ast_node is None:
        return None
    _fields = ast_node._fields
    if (cls := ast_node.__class__) in (ast.If, ast.Assign, ast.FunctionDef, ast.For, ast.While, ast.With):
        _fields = (*_fields, 'lineno')
    return cls(**{field: ast_copy(ast_field) if isinstance((ast_field := getattr(ast_node, field, None)), ast.AST) else [ast_copy(ast_item) for ast_item in ast_field] if ast_field.__class__ == list else ast_field for field in _fields})

def add_at_the_module_beginning(ast_module, ast_node):
    """Adds ast_node after module docstring and future imports"""
    ymacro_ast_module = ast_module
    position = 1 if ymacro_ast_module.__class__ == ast.Module and ymacro_ast_module.body[0].__class__ == ast.Expr and (ymacro_ast_module.body[0].value.__class__ == ast.Constant) and (ymacro_ast_module.body[0].value.value == str) else 0
    while ymacro_ast_module.body[position].__class__ == ast.ImportFrom and ymacro_ast_module.body[position].module == '__future__':
        position += 1
    ast_module.body.insert(position, ast_node)

def strip_module_docstring(ast_module):
    assert ast_module.__class__ == ast.Module
    if (ex := ast_module.body[0]).__class__ == ast.Expr and ex.value.__class__ == ast.Constant and (ex.value.value.__class__ == str):
        return ast_module.body.pop(0)

class TransformError(BaseException):
    ...
YMF_hygienic = 1 << 0
YMF_mLang = 1 << 1
YMF_expr = 1 << 2
YMF_XMacro = 1 << 3
YMF_YMacro = 1 << 4
YMF_ZMacro = 1 << 5

def def_macro(*args, hygienic=False, mLang=False, expr=False, XMacro=False, YMacro=False, ZMacro=False, **kwargs):
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
    if isinstance(_ast, ast.Constant):
        return _ast.value
    elif isinstance(_ast, ast.UnaryOp) and isinstance(_ast.op, ast.USub):
        return -mLang_conv(_ast.operand)
    elif isinstance(_ast, (ast.List, ast.Tuple)):
        return [mLang_conv(el) for el in _ast.elts]
    raise NotImplementedError(f'convert {ast.dump(_ast)}')
restricted_builtins = {k: v for (k, v) in __builtins__.items() if not k.startswith('_') and k not in ('credits', 'help', 'license', 'copyright', 'exit', 'open', 'quit', 'compile', 'eval', 'exec')}

# Amalgamating from yeastr/minimal_runtime.py
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
    if obj.__class__.__flags__ & 32:
        return True
    return isinstance(obj, (Sequence, array, deque)) and (not isinstance(obj, (str, bytes, bytearray)))

def ymatch_as_map(obj):
    if obj.__class__.__flags__ & 64:
        return True
    return isinstance(obj, (Mapping, dict, MappingProxyType))

def ymatch_positional_origin(obj):
    if hasattr(obj, '__dataclass_fields__'):
        return list(obj.__dataclass_fields__.keys())
    if hasattr(obj, '__match_args__'):
        return obj.__match_args__

def random_string(length):
    return ''.join([f'{x:0x}' for x in randbytes(length // 2)])

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
    return dict(*map(lambda args: _map(*args), filter(lambda args: _fil(*args), _iter)))

# Amalgamating from yeastr/impl_macros.pyy
class Macros:
    """Contains all the macros"""

    def __init__(self):
        self._macros = {}

    def add(self, fn, flags, _args, kwargs):
        """The actual @def_macro() decorator may call this

        Here fn is the decorated function that is inspected to get the source
        for the macro that gets added"""
        fn.ym_flags = flags
        fn.ymacrokw = kwargs
        if hasattr(fn, '_source'):
            source = fn._source
        else:
            _source = getsource(fn)
            indent = len(re.compile('^(\\s*)\\S*').match(_source).group(1))
            source = ''
            multiline_string = False
            for line in _source.splitlines():
                if multiline_string is False:
                    line = line[indent:]
                    if len((matches := re.compile('("""|\'\'\')').findall(line))) == 1:
                        multiline_string = matches[0]
                elif len(re.compile(multiline_string).findall(line)) == 1:
                    multiline_string = False
                if not source and line.startswith('@'):
                    continue
                source += line + '\n'
            del _source
        _fn = ast.parse(source)
        del source
        _ast = _fn.body[0].body
        if _ast[0].__class__ == ast.Expr and _ast[0].value.__class__ == ast.Constant and (_ast[0].value.value.__class__ == str):
            _ast.pop(0)
        self._macros.update({fn.name: (fn, _ast)})

    def add_ast(self, fn, name, _ast, flags, _args, kwargs):
        """The usual @def_macro and @def_macro() may call this"""
        bmacro = fn
        bmacro.name = name
        bmacro.ym_flags = flags
        bmacro.ymacrokw = kwargs
        self._macros.update({name: (fn, _ast)})

    def retrieve(self, ast_node, required=False):
        """
        :param ast_node: of the macro to retrieve
        :type ast_node: ast.Name

        :param required: raise when not found, dumping the name of all knowing macros, defaults to False
        :type required: bool

        :returns: A copy of the body of the macro as the last element of the returned tuple
        :rtype: Tuple[str, Any, List[ast.AST]]
        """
        if ast_node.__class__ == ast.Name:
            mname = ast_node.id
            if (duple := self._macros.get(mname)) is not None:
                return (mname, duple[0], ast_copy(duple[1]))
        if required:
            raise TransformError(f'Macro {ast_node.id} missing. known: {list(self._macros.keys())}')
_macros = Macros()

# Getting macros from yeastr/impl_namedloops.pyy
# Getting macros from yeastr/impl_call2comp.pyy
# Getting macros from yeastr/backport_fstring_backslash.pyy
# Getting macros from yeastr/backport_match.pyy
# Getting macros from yeastr/backport_dict_ops.pyy
# Amalgamating from yeastr/build_time_transformer.pyy
_bfb_0a__ = '\n'

class BuildTimeTransformer:

    def __init__(self, file_content, pyver, /, autoimport='minimal_runtime', strip_module_docstring=False):
        """Parses source and setups the transformations

        :param file_content: Abstract source code using the python syntax
        :type file_content: str

        :param pyver: PEP425 target, used to backport
        :type pyver: str

        :param autoimport: should be one of:

            - False/None (no autoimport at all)
            - minimal_runtime (backport match, call2comp fallbacks)
            - bootstrapped (the whole thing)
            - import_hooks (imports bootstrapped and enables ihooks for .ypy files)
            - as_decorator (the whole thing but exposed through decorators instead)
        :type autoimport: str | False | None

        :param strip_module_docstring: (kept in ``self.ast`` until you call yang)
        :type strip_module_docstring: bool
       """
        self.ast = ast.parse(file_content)
        self.version_info = (int(pyver[2]), int(pyver[3:].split('-', 1)[0]))
        self.autoimport = autoimport
        self.strip_module_docstring = strip_module_docstring

    def yang(self, macros):
        """Apply the transformations

        :param macros: macros yeastr knows about
        :type macros: Macros

        :returns: tranformed source code
        :rtype: str
        """
        if self.strip_module_docstring:
            strip_module_docstring(self.ast)
        _yfor_def_macro_stage_iter = self.ast.body
        _yfor_def_macro_stage_i = 0
        yloopsf = 0
        while _yfor_def_macro_stage_i < len(_yfor_def_macro_stage_iter):
            tln = _yfor_def_macro_stage_iter[_yfor_def_macro_stage_i]
            if 'decorator_list' in tln._fields:
                if 'def_macro' in (dec.func.id if dec_call else dec.id for dec in tln.decorator_list if (dec_ := dec) and (dec_call := (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name))) or isinstance(dec, ast.Name)):
                    if not dec_call:
                        dec_index = tln.decorator_list.index(dec_)
                        tln.decorator_list[dec_index] = ast.Call(func=ast.Name('def_macro'), args=[], keywords=[])
                    macro_ast = tln.body
                    ymacro_node = tln
                    assert not ymacro_node.args.defaults, 'macro cannot have defaults, put kwargs on def_macro itself'
                    args = ymacro_node.args.args
                    call = [call for call in tln.decorator_list if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and (call.func.id == 'def_macro')][0]
                    marg0 = len(call.args) > 0 and call.args[0].__class__ == ast.Name and call.args[0].id
                    kwargs = {k.arg: mLang_conv(k.value) for k in call.keywords}
                    strip = 'strip_def' if kwargs.get('strip', True) else 'strip_strip'
                    flags = 0
                    if kwargs.get('hygienic', False):
                        flags |= YMF_hygienic
                    if kwargs.get('mLang', False):
                        flags |= YMF_mLang
                    if kwargs.get('expr', False) or 'E' == marg0:
                        flags |= YMF_expr
                    elif kwargs.get('XMacro', False) or 'X' == marg0:
                        flags |= YMF_XMacro
                    elif kwargs.get('YMacro', False) or 'Y' == marg0:
                        flags |= YMF_YMacro
                    elif kwargs.get('ZMacro', False) or 'Z' == marg0:
                        flags |= YMF_ZMacro
                    assert not (flags & YMF_expr and flags & YMF_hygienic), "just doesn't make sense... it does but wait..."
                    if strip == 'strip_def':
                        if 'hygienic' in kwargs:
                            del kwargs['hygienic']
                        if 'mLang' in kwargs:
                            del kwargs['mLang']
                        mnode = ast_copy(tln)
                        assert len(mnode.decorator_list) == 1, 'TODO: What to do with other decorators?'
                        mnode.decorator_list = []
                        _here = {'ast': ast}
                        exec(compile(ast.unparse(mnode), f'_m_{tln.name}.py', 'exec'), _here)
                        ymacro__ast = macro_ast
                        if ymacro__ast[0].__class__ == ast.Expr and ymacro__ast[0].value.__class__ == ast.Constant and (ymacro__ast[0].value.value.__class__ == str):
                            ymacro__ast.pop(0)
                        if flags & YMF_expr and (not flags & YMF_mLang) and (len(macro_ast) > 1):
                            assert False, "You're using it wrong. (TODO: Provide explainations)"
                        macros.add_ast(_here[tln.name], tln.name, macro_ast, flags, args, kwargs)
                        del _yfor_def_macro_stage_iter[_yfor_def_macro_stage_i]
                        _yfor_def_macro_stage_i -= 1
                    elif strip == 'strip_strip':
                        _yfor_kwloop_iter = call.keywords
                        _yfor_kwloop_i = 0
                        while _yfor_kwloop_i < len(_yfor_kwloop_iter):
                            kw = _yfor_kwloop_iter[_yfor_kwloop_i]
                            if kw.arg == 'strip':
                                del _yfor_kwloop_iter[_yfor_kwloop_i]
                                
                                break
                            _yfor_kwloop_i += 1
                            assert _yfor_kwloop_i >= 0, 'u screwed up.. I mean, down, yep, up\nu screwed up!'
                        mnode = ast_copy(tln)
                        assert len(mnode.decorator_list) == 1, 'TODO: What to do with other decorators?'
                        mnode.decorator_list = []
                        _here = {'ast': ast}
                        exec(compile(ast.unparse(mnode), f'_m_{tln.name}.py', 'exec'), _here)
                        ymacro__ast = macro_ast
                        if ymacro__ast[0].__class__ == ast.Expr and ymacro__ast[0].value.__class__ == ast.Constant and (ymacro__ast[0].value.value.__class__ == str):
                            ymacro__ast.pop(0)
                        if flags & YMF_expr and (not flags & YMF_mLang) and (len(macro_ast) > 1):
                            assert False, "You're using it wrong. (TODO: Provide explainations)"
                        macros.add_ast(_here[tln.name], tln.name, macro_ast, flags, args, kwargs)
                    else:
                        raise NotImplementedError("well, that's new")
            _yfor_def_macro_stage_i += 1
            assert _yfor_def_macro_stage_i >= 0, 'u screwed up.. I mean, down, yep, up\nu screwed up!'
        ymacro_never_defer = False
        ymacro_some_ast = self.ast
        ymacro_macros_ = macros
        mp = 'ymacro_%s'
        deferred_macroe = []
        with MoonGrabber() as macro_keepalive:

            def filter_macro_moons(moon):
                ymacro__macros = ymacro_macros_
                needs_expansion = moon.node.__class__ == ast.Call and moon.node.func.__class__ in (ast.Name, ast.Attribute) and (moon.node not in deferred_macroe) and ((retrieved := ymacro__macros.retrieve(moon.node.func)) is not None)
                if needs_expansion:
                    moon.retrieved = retrieved
                    macro_keepalive(moon, moon.up, moon.up.up)
                    return moon
            depth_counter = 0
            depth_limit = 500
            macro_moons = list(MoonWalking(ymacro_some_ast, filter_cb=filter_macro_moons).tree)
            yloopsf = 0
            while macro_moons:
                if depth_counter > depth_limit:
                    raise RecursionError(f'macro expansion limit({depth_limit}): ' + ', '.join((moon.retrieved[0] for moon in macro_moons)))
                if ymacro_never_defer:
                    deferred_macroe = []
                for _yfor_macroexpansionloop_it in macro_moons:
                    moon = _yfor_macroexpansionloop_it
                    retrieved = moon.retrieved
                    ymacro__macros = ymacro_macros_
                    (mname, fn__, _ast) = retrieved
                    _yfor_kwdloop_iter = moon.node.keywords
                    _yfor_kwdloop_end = len(_yfor_kwdloop_iter)
                    _yfor_kwdloop_i = 0
                    while _yfor_kwdloop_i < _yfor_kwdloop_end:
                        arg = _yfor_kwdloop_iter[_yfor_kwdloop_i]
                        if arg.arg == 'defer_expansion' and isinstance(arg.value, ast.Constant) and arg.value.value:
                            del _yfor_kwdloop_iter[_yfor_kwdloop_i]
                            deferred_macroe.append(moon.node)
                            yloopsf = 4
                            break
                        _yfor_kwdloop_i += 1
                        assert _yfor_kwdloop_i >= 0, 'u screwed up.. I mean, down, yep, up\nu screwed up!'
                    if yloopsf & 4:
                        yloopsf = 0
                        continue
                    if fn__.ym_flags & YMF_XMacro:
                        if fn__.ym_flags & YMF_hygienic:
                            assert all((p is None for p in where)), 'incompatibilities?'
                        if fn__.ym_flags & YMF_mLang:
                            raise NotImplementedError('X Macro with mLang')
                        assert len(moon.node.args) == 1, 'mismatching XMacro(YMacro) arity'
                        assert moon.node.args[0].__class__ == ast.Name, 'bad XMacro(YMacro) param'
                        if moon.node.args[0].id == 'len':
                            moon.expanded = [ast.Constant(len(_ast))]
                            moon.was_len = True
                        else:
                            moon.was_len = False
                            (xYname, xYfn, xYast) = _macros.retrieve(moon.node.args[0], required=True)
                            assert xYfn.ym_flags & YMF_YMacro, ast.unparse(moon.up.node)
                            if xYfn.ym_flags & YMF_mLang:
                                raise NotImplementedError('Y Macro with mLang')
                            ym_params = list(signature(xYfn).parameters.keys())
                            ym_quoted = [f'{p}_quoted' for p in ym_params]
                            moon.expanded = []
                            with MoonGrabber() as keepalive:

                                def moon_filter(moon):
                                    if moon.node.__class__ == ast.Name and ((fpname := (moon.node.id in ym_params)) or moon.node.id in ym_quoted):
                                        moon.argname = moon.node.id
                                        moon.suffix = ''
                                        if not fpname:
                                            moon.suffix = '_quoted'
                                        keepalive(moon.up)
                                        return moon
                                    elif moon.node.__class__ == str and f'{ym_params[0]}_token' in moon.node:
                                        moon.suffix = '_token'
                                        moon.up
                                        return moon
                                for _x in _ast:
                                    if not (_x.__class__ == ast.Expr and (xname := _x.value).__class__ == ast.Name and (xstr := xname.id)):
                                        raise NotImplementedError('XMacro is not a list of names, this is TODO')
                                    preserved_xYast = ast_copy(xYast)
                                    fake_module = ast.Module(body=preserved_xYast)
                                    for _yfor_xymoons_it in MoonWalking(fake_module, filter_cb=moon_filter).tree:
                                        if _yfor_xymoons_it.suffix == '_quoted':
                                            _yfor_xymoons_it.replace(ast.Constant(xstr))
                                        elif _yfor_xymoons_it.suffix == '_token':
                                            _yfor_xymoons_it.replace_str(re.sub(f'{ym_params[0]}_token', xstr, _yfor_xymoons_it.node))
                                        else:
                                            _yfor_xymoons_it.replace(ast.Name(xstr, ctx=_yfor_xymoons_it.node.ctx))
                                    moon.expanded.extend(preserved_xYast)
                    elif fn__.ym_flags & YMF_ZMacro:
                        assert moon.node.args[0].__class__ == ast.Name, 'bad ZMacro 1st param, must be XMacro'
                        assert moon.node.args[1].__class__ == ast.Name, 'bad ZMacro 2nd param, must be a name'
                        if fn__.ym_flags & YMF_hygienic:
                            raise NotImplementedError('Z Macro with hygienic')
                        if fn__.ym_flags & YMF_mLang:
                            raise NotImplementedError('Z Macro with mLang')
                        z_params = list(signature(fn__).parameters.keys())
                        if len(moon.node.args) != 2:
                            raise NotImplementedError('Z(X, E) macro, check arity')
                        if any((arg.__class__ != ast.Name for arg in moon.node.args)):
                            raise NotImplementedError('Z args must be static known names')
                        (zXname, zXfn, zXast) = _macros.retrieve(moon.node.args[0], required=True)
                        assert zXfn.ym_flags & YMF_XMacro
                        if zXfn.ym_flags & YMF_mLang:
                            raise NotImplementedError('X Macro with mLang')
                        with MoonGrabber() as keepalive:

                            def moon_filter(zmoon):
                                if zmoon.node.__class__ == ast.Name and ((unquoted := (zmoon.node.id in z_params)) or (zmoon.node.id.endswith('_quoted') and zmoon.node.id[:-len('_quoted')] in z_params)):
                                    if unquoted:
                                        zmoon.param_i = z_params.index(zmoon.node.id)
                                        zmoon.quoted = False
                                    else:
                                        zmoon.param_i = z_params.index(zmoon.node.id[:-len('_quoted')])
                                        zmoon.quoted = True
                                    keepalive(zmoon.up)
                                    return zmoon

                            def moon_walk(moonwalker):
                                yloopsf = 0
                                for _n in moonwalker.tree:
                                    if _n.param_i == 0:
                                        _n.replace(ast.Tuple(elts=[ast.Constant(x.value.id) if _n.quoted else x.value for x in zXast]))
                                    else:
                                        _n.node.id = moon.node.args[_n.param_i].id
                                return True
                            for ast__ in _ast:
                                MoonWalking(ast__, filter_cb=moon_filter, before_reversing_cb=moon_walk)
                    elif fn__.ym_flags & YMF_expr:
                        formal_params = list(signature(fn__).parameters.keys())
                        with MoonGrabber() as keepalive:

                            def moon_filter(moon):
                                if moon.node.__class__ == ast.Name and moon.node.id in formal_params:
                                    keepalive(moon.up)
                                    return moon

                            def moon_walk(moonwalker):
                                yloopsf = 0
                                for _n in moonwalker.tree:
                                    _n.replace(ast.Name(formal_params[formal_param_i]) if (actual_param := moon.node.args[(formal_param_i := formal_params.index(_n.node.id))]).__class__ == ast.Name and (actual_param := moon.node.args[(formal_param_i := formal_params.index(_n.node.id))]).id == '_' else actual_param)
                                return True
                            for ast__ in _ast:
                                MoonWalking(ast__, filter_cb=moon_filter, before_reversing_cb=moon_walk)
                    else:
                        if not isinstance(moon.up.node, ast.Expr):
                            raise NotImplementedError(f'macro expansion within {moon.up.node.__class__}')
                        where = [p[3:] if p.startswith('yr_') else None for p in signature(fn__).parameters.keys()]
                        if fn__.ym_flags & YMF_hygienic:
                            assert all((p is None for p in where)), 'incompatibilities?'
                        replacements = []
                        with MoonGrabber() as keepalive:

                            def moon_filter(moon):
                                if moon.node.__class__ == ast.Name and moon.node.id in where:
                                    keepalive(moon.up)
                                    return moon

                            def moon_walk(moonwalker):
                                yloopsf = 0
                                for _n in moonwalker.tree:
                                    arg = moon.node.args[where.index(_n.node.id)]
                                    _n.replace(arg)
                                    replacements.append(arg)
                                return True
                            for ast__ in _ast:
                                MoonWalking(ast__, filter_cb=moon_filter, before_reversing_cb=moon_walk)
                    if fn__.ym_flags & YMF_mLang:
                        mglobals = {'ast': ast, '__builtins__': restricted_builtins}
                        mEval_ctx = {'__builtins__': restricted_builtins}
                        ymacrokw = fn__.ymacrokw
                        mlocals = dict(ymacrokw)
                        mlocals.update({k.arg: mLang_conv(k.value) for k in moon.node.keywords if k.arg in ymacrokw.keys()})

                        def perform(starting_node, next_node=None):
                            if starting_node.__class__ == ast.With and isinstance((what := starting_node.items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'mIf'):
                                if eval(compile(ast.unparse(call.args[0]), '_mLang.py', 'eval'), mglobals, mlocals):
                                    if next_node.__class__ == ast.With and isinstance((what := next_node.items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'mElse'):
                                        return ('skip-else', starting_node.body)
                                    return ('then', starting_node.body)
                                elif next_node.__class__ == ast.With and isinstance((what := next_node.items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'mElse'):
                                    return ('otherwise', next_node.body)
                                else:
                                    return ('skip', [])
                            elif starting_node.__class__ == ast.Call and starting_node.func.__class__ == ast.Name and (starting_node.func.id == 'mEval'):
                                return ('mEval', ast.parse(str(eval(ast.unparse(starting_node.args[0]), mEval_ctx)), '_mEval.py', 'eval').body)
                            fields = [(field, getattr(starting_node, field)) for field in starting_node._fields if hasattr(starting_node, field)]
                            yloopsf = 0
                            for _yfor_fields_loop_it in fields:
                                (field, mbody_ast_field) = _yfor_fields_loop_it
                                if isinstance(mbody_ast_field, list):
                                    _yfor_subnodes_loop_iter = mbody_ast_field
                                    _yfor_subnodes_loop_i = 0
                                    while _yfor_subnodes_loop_i < len(_yfor_subnodes_loop_iter):
                                        subnode = _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i]
                                        try:
                                            (action, new_body) = perform(subnode, _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i + 1])
                                        except IndexError:
                                            (action, new_body) = perform(subnode)
                                        if action is None:
                                            ...
                                        elif action == 'skip':
                                            assert _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i].__class__ == ast.With and isinstance((what := _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i].items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'mIf')
                                            del _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i]
                                            _yfor_subnodes_loop_i = max(_yfor_subnodes_loop_i - 1, -1)
                                        elif action in ('otherwise', 'skip-else'):
                                            assert _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i].__class__ == ast.With and isinstance((what := _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i].items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'mIf')
                                            del _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i]
                                            assert _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i].__class__ == ast.With and isinstance((what := _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i].items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'mElse')
                                            del _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i]
                                            _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i:_yfor_subnodes_loop_i] = new_body
                                            _yfor_subnodes_loop_i = max(_yfor_subnodes_loop_i - 2, -1)
                                        elif action in ('then', 'mEval'):
                                            assert _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i].__class__ == ast.With and isinstance((what := _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i].items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == ('mIf' if action == 'then' else 'mEval'))
                                            del _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i]
                                            _yfor_subnodes_loop_iter[_yfor_subnodes_loop_i:_yfor_subnodes_loop_i] = new_body
                                            _yfor_subnodes_loop_i -= 1
                                            _yfor_subnodes_loop_i = max(_yfor_subnodes_loop_i - 1, -1)
                                        else:
                                            assert False, f"unexpected {action} ({'nested'})"
                                        _yfor_subnodes_loop_i += 1
                                        assert _yfor_subnodes_loop_i >= 0, 'u screwed up.. I mean, down, yep, up\nu screwed up!'
                                elif isinstance(mbody_ast_field, ast.AST):
                                    (action, new_node) = perform(mbody_ast_field, next_node)
                                    if action == 'mEval':
                                        setattr(starting_node, field, new_node)
                                    elif action is None:
                                        ...
                                    else:
                                        assert False, f'unexpected {action} (field)'
                            return (None, None)
                        _yfor_mbody_loop_iter = _ast
                        _yfor_mbody_loop_i = 0
                        while _yfor_mbody_loop_i < len(_yfor_mbody_loop_iter):
                            mbody_ast = _yfor_mbody_loop_iter[_yfor_mbody_loop_i]
                            try:
                                (action, new_body) = perform(mbody_ast, _yfor_mbody_loop_iter[_yfor_mbody_loop_i + 1])
                            except IndexError:
                                (action, new_body) = perform(mbody_ast)
                            assert action != 'mEval', 'unexpected mEval at top'
                            if action is None:
                                ...
                            elif action == 'skip':
                                assert _yfor_mbody_loop_iter[_yfor_mbody_loop_i].__class__ == ast.With and isinstance((what := _yfor_mbody_loop_iter[_yfor_mbody_loop_i].items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'mIf')
                                del _yfor_mbody_loop_iter[_yfor_mbody_loop_i]
                                _yfor_mbody_loop_i = max(_yfor_mbody_loop_i - 1, -1)
                            elif action in ('otherwise', 'skip-else'):
                                assert _yfor_mbody_loop_iter[_yfor_mbody_loop_i].__class__ == ast.With and isinstance((what := _yfor_mbody_loop_iter[_yfor_mbody_loop_i].items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'mIf')
                                del _yfor_mbody_loop_iter[_yfor_mbody_loop_i]
                                assert _yfor_mbody_loop_iter[_yfor_mbody_loop_i].__class__ == ast.With and isinstance((what := _yfor_mbody_loop_iter[_yfor_mbody_loop_i].items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'mElse')
                                del _yfor_mbody_loop_iter[_yfor_mbody_loop_i]
                                _yfor_mbody_loop_iter[_yfor_mbody_loop_i:_yfor_mbody_loop_i] = new_body
                                _yfor_mbody_loop_i = max(_yfor_mbody_loop_i - 2, -1)
                            elif action in ('then', 'mEval'):
                                assert _yfor_mbody_loop_iter[_yfor_mbody_loop_i].__class__ == ast.With and isinstance((what := _yfor_mbody_loop_iter[_yfor_mbody_loop_i].items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == ('mIf' if action == 'then' else 'mEval'))
                                del _yfor_mbody_loop_iter[_yfor_mbody_loop_i]
                                _yfor_mbody_loop_iter[_yfor_mbody_loop_i:_yfor_mbody_loop_i] = new_body
                                _yfor_mbody_loop_i -= 1
                                _yfor_mbody_loop_i = max(_yfor_mbody_loop_i - 1, -1)
                            else:
                                assert False, f"unexpected {action} ({'top'})"
                            _yfor_mbody_loop_i += 1
                            assert _yfor_mbody_loop_i >= 0, 'u screwed up.. I mean, down, yep, up\nu screwed up!'
                        _yfor_mbody_loop_iter = _ast
                        _yfor_mbody_loop_i = 0
                        while _yfor_mbody_loop_i < len(_yfor_mbody_loop_iter):
                            mbody_ast = _yfor_mbody_loop_iter[_yfor_mbody_loop_i]
                            if any((_yfor_mbody_loop_iter[_yfor_mbody_loop_i].__class__ == ast.With and isinstance((what := _yfor_mbody_loop_iter[_yfor_mbody_loop_i].items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == unexpected) for unexpected in ('mIf', 'mElse', 'mEval'))):
                                breakpoint()
                            _yfor_mbody_loop_i += 1
                            assert _yfor_mbody_loop_i >= 0, 'u screwed up.. I mean, down, yep, up\nu screwed up!'
                    if fn__.ym_flags & YMF_expr:
                        if len(_ast) > 1:
                            raise TransformError(f"{'expression'} macro expanded into multiple expressions")
                        moon.replace(_ast[0].value)
                    elif fn__.ym_flags & YMF_XMacro:
                        if moon.was_len:
                            moon.up.replace(moon.expanded[0])
                        else:
                            assert moon.up.node.__class__ == ast.Expr, f'did you want Z(W) instead of X(Y)? {ast.unparse(moon.up.node)}'
                            moon.up.pop_extend(moon.expanded)
                    elif fn__.ym_flags & YMF_ZMacro:
                        if len(_ast) > 1:
                            raise TransformError(f"{'Z'} macro expanded into multiple expressions")
                        moon.replace(_ast[0].value)
                    else:
                        if fn__.ym_flags & (YMF_expr | YMF_XMacro | YMF_YMacro | YMF_ZMacro):
                            raise TransformError(f'Incorrect expansion of {mname}')
                        assignments = []
                        for (_yfor_l_i, _yfor_l_it) in enumerate(signature(fn__).parameters):
                            try:
                                ass = ast.Assign(targets=[ast.Name(id=mp % _yfor_l_it)], value=moon.node.args[_yfor_l_i], lineno=1)
                            except IndexError:
                                raise TransformError(f'wrong arity {_yfor_l_i} (missing {_yfor_l_it}) in {ast.unparse(moon.node)}')
                            if ass.value not in replacements:
                                _ast.insert(0, ass)
                                assignments.append(ass)
                        where = fn__.__code__.co_varnames if fn__.ym_flags & YMF_hygienic else signature(fn__).parameters

                        def moon_filter(moon):
                            if isinstance(moon.node, ast.Name) and moon.node.id in where and (moon.up.node not in assignments) and (moon.node not in replacements):
                                return moon

                        def moon_walk(moonwalker):
                            yloopsf = 0
                            for _n in moonwalker.tree:
                                _n.node.id = mp % _n.node.id
                            return True
                        for ast__ in _ast:
                            MoonWalking(ast__, filter_cb=moon_filter, before_reversing_cb=moon_walk)
                        moon.up.pop_extend(_ast)
                if yloopsf:
                    break
                macro_keepalive.reset()
                macro_moons = list(MoonWalking(ymacro_some_ast, filter_cb=filter_macro_moons).tree)
                depth_counter += 1
        backported_fstring = set()
        if self.version_info < (3, 12):
            _x_escapes = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 173, *range(177, 256)]
            with MoonGrabber() as grab:

                def moon_filter(moon):
                    if moon.node.__class__ == ast.Constant and isinstance(moon.node.value, str):
                        if moon.upper(ast.JoinedStr):
                            moon.x_escaped = []
                            moon.u_escaped = []
                            yloopsf = 0
                            for (_yfor_charloop_i, _yfor_charloop_it) in enumerate(moon.node.value):
                                ch = _yfor_charloop_it
                                if ord(ch) in _x_escapes:
                                    moon.x_escaped.append(_yfor_charloop_i)
                                elif ord(ch) > 255:
                                    moon.u_escaped.append(_yfor_charloop_i)
                            if moon.x_escaped or moon.u_escaped:
                                return moon
                yloopsf = 0
                for moon in MoonWalking(self.ast, filter_cb=moon_filter).tree:
                    inner_fstring = ast.JoinedStr(values=(inner_values := []))
                    buffer = ''
                    new_names = set()
                    for (_yfor_charloop_i, _yfor_charloop_it) in enumerate(moon.node.value):
                        ch = _yfor_charloop_it
                        if (nx := (_yfor_charloop_i not in moon.x_escaped)) and _yfor_charloop_i not in moon.u_escaped:
                            buffer += _yfor_charloop_it
                        elif nx:
                            inner_values.extend([ast.Constant(buffer), ast.FormattedValue(value=ast.Name((new_name := f'_bfb_{ord(ch):08x}__')), conversion=-1)])
                            new_names.add(new_name)
                            buffer = ''
                        else:
                            inner_values.extend([ast.Constant(buffer), ast.FormattedValue(value=ast.Name((new_name := f'_bfb_{ord(ch):02x}__')), conversion=-1)])
                            new_names.add(new_name)
                            buffer = ''
                    if buffer:
                        inner_values.append(ast.Constant(buffer))
                    moon.replace(inner_fstring)
                    backported_fstring |= new_names
        if self.version_info < (3, 10):

            def backport_MatchValue_to_expr(subj, match_value):
                return ast.Compare(left=subj, ops=[ast.Eq()], comparators=[match_value.value])

            def backport_MatchSingleton_to_expr(subj, match_singleton):
                return ast.Compare(left=ast.Constant(match_singleton.value), ops=[ast.Is()], comparators=[subj])

            def backport_MatchAs_to_expr(subj, match_as):
                if match_as.pattern:
                    assert match_as.name
                    return ast.BoolOp(op=ast.And(), values=[backport_dispatch_match(subj, match_as.pattern), ast.BoolOp(op=ast.Or(), values=[ast.NamedExpr(target=ast.Name(match_as.name), value=subj), ast.Constant(True)])])
                if (patname := match_as.name):
                    return ast.BoolOp(op=ast.Or(), values=[ast.NamedExpr(target=ast.Name(patname), value=subj), ast.Constant(True)])
                else:
                    return ast.Constant(True)

            def backport_MatchOr_to_expr(subj, match_or):
                return ast.BoolOp(op=ast.Or(), values=[backport_dispatch_match(subj, pat) for pat in match_or.patterns])

            def backport_MatchSequence_to_expr(subj, match_seq):
                seq_check = ast.Call(func=ast.Name('ymatch_as_seq'), args=[subj], keywords=[])
                seq_len_check = ast.Compare(left=ast.Constant(len([True for pat in match_case.pattern.patterns if not isinstance(pat, ast.MatchStar)])), ops=[ast.Lt()], comparators=[ast.Call(func=ast.Name('len'), args=[subj], keywords=[])]) if any((isinstance(pat, ast.MatchStar) for pat in match_seq.patterns)) else ast.Compare(left=ast.Constant(len(match_seq.patterns)), ops=[ast.Eq()], comparators=[ast.Call(func=ast.Name('len'), args=[subj], keywords=[])])
                exprs = []
                star = False
                yloopsf = 0
                for (idx, subpattern) in enumerate(match_seq.patterns):
                    subsubj = ast.Subscript(value=subj, slice=ast.Constant(idx) if not star else ast.UnaryOp(op=ast.USub(), operand=ast.Constant(len(match_seq.patterns) - idx)))
                    if isinstance(subpattern, ast.MatchStar):
                        star = idx
                        exprs.append(backport_MatchStar_to_expr(subj, subpattern, len(match_seq.patterns), idx))
                    else:
                        exprs.append(backport_dispatch_match(subsubj, subpattern))
                return ast.BoolOp(op=ast.And(), values=[seq_check, seq_len_check, *exprs])

            def backport_MatchStar_to_expr(subj, match_star, len_, pos):
                return ast.BoolOp(op=ast.Or(), values=[ast.NamedExpr(target=ast.Name(match_star.name if match_star.name else '_'), value=ast.Subscript(value=subj, slice=ast.Slice(lower=ast.Constant(pos), upper=ast.BinOp(left=ast.Call(func=ast.Name('len'), args=[subj], keywords=[]), op=ast.Sub(), right=ast.Constant(len_ - pos - 1))))), ast.Constant(True)])

            def backport_MatchClass_to_expr(subj, match_class):
                positional_matchers = []
                yloopsf = 0
                for (pati, pat_) in enumerate(match_class.patterns):
                    patsubj = ast.Call(func=ast.Name('getattr'), args=[subj, ast.Subscript(value=ast.Call(func=ast.Name('ymatch_positional_origin'), args=[subj]), slice=ast.Constant(pati))], keywords=[])
                    positional_matchers.append(backport_dispatch_match(patsubj, pat_))
                explicit_matchers = []
                yloopsf = 0
                for (kwi, kwd) in enumerate(match_class.kwd_attrs):
                    kwdsubj = ast.Attribute(value=subj, attr=kwd)
                    pexpr = ast.BoolOp(op=ast.And(), values=[ast.Call(func=ast.Name('hasattr'), args=[subj, ast.Constant(kwd)], keywords=[]), ast.BoolOp(op=ast.Or(), values=[ast.NamedExpr(target=ast.Name(kwd), value=kwdsubj), ast.Constant(True)])])
                    kwdpat = match_class.kwd_patterns[kwi]
                    pexpr.values.append(backport_dispatch_match(kwdsubj, kwdpat))
                    explicit_matchers.append(pexpr)
                return ast.BoolOp(op=ast.And(), values=[ast.Call(func=ast.Name('isinstance'), args=[subj, match_class.cls], keywords=[]), *positional_matchers, *explicit_matchers])

            def backport_MatchMapping_to_expr(subj, match_mapping):
                matchers = []
                yloopsf = 0
                for (key, pat) in zip(match_mapping.keys, match_mapping.patterns):
                    matchers.append(ast.Compare(left=key, ops=[ast.In()], comparators=[subj]))
                    get_ = ast.Attribute(value=subj, attr='get')
                    patsubj = ast.Call(func=get_, args=[key], keywords=[])
                    matchers.append(backport_dispatch_match(patsubj, pat))
                    if match_mapping.rest:
                        matchers.append(ast.BoolOp(op=ast.Or(), values=[ast.NamedExpr(target=ast.Name(match_mapping.rest), value=ast.DictComp(key=ast.Name('k'), value=ast.Name('v'), generators=[ast.comprehension(target=ast.Tuple(elts=[ast.Name('k'), ast.Name('v')]), iter=ast.Call(func=ast.Attribute(value=subj, attr='items'), args=[], keywords=[]), ifs=[ast.Compare(left=ast.Name('k'), ops=[ast.NotIn()], comparators=[ast.Tuple(elts=match_mapping.keys)])], is_async=0)])), ast.Constant(value=True)]))
                return ast.BoolOp(op=ast.And(), values=[ast.Call(func=ast.Name('ymatch_as_map'), args=[subj], keywords=[]), *matchers])

            def backport_MatchCase_to_if(subj, match_case):
                expr = backport_dispatch_match(subj, match_case.pattern)
                return ast.If(test=ast.BoolOp(op=ast.And(), values=[expr, match_case.guard]) if match_case.guard else expr, body=match_case.body, orelse=[])

            def backport_dispatch_match(subj, pat):
                return {ast.MatchAs: backport_MatchAs_to_expr, ast.MatchSingleton: backport_MatchSingleton_to_expr, ast.MatchValue: backport_MatchValue_to_expr, ast.MatchOr: backport_MatchOr_to_expr, ast.MatchSequence: backport_MatchSequence_to_expr, ast.MatchClass: backport_MatchClass_to_expr, ast.MatchMapping: backport_MatchMapping_to_expr}[type(pat)](subj, pat)
            match_counter = 0

            def moon_filter(moon):
                if isinstance(moon.node, ast.Match):
                    moon.up
                    return moon
            yloopsf = 0
            for moon in MoonWalking(self.ast, filter_cb=moon_filter).tree:
                match_subject = moon.node.subject
                new_body = [ast.Assign(targets=[(subj := ast.Name('ymatch_%d_subject' % match_counter))], value=match_subject, lineno=1)]
                new_body.append(backport_MatchCase_to_if(subj, moon.node.cases[0]))
                orelse = new_body[-1].orelse
                for match_case in moon.node.cases[1:]:
                    orelse.append((last_if := backport_MatchCase_to_if(subj, match_case)))
                    orelse = last_if.orelse
                moon.pop_extend(new_body)
                match_counter += 1

        def before_the_loop(moon):
            if moon.flags & NEEDS_YLOOPSF:
                return ast.Assign(targets=[ast.Name('yloopsf')], value=ast.Constant(0), lineno=1)

        def after_the_loop(moon):
            if moon.loop_depth == 0:
                return None
            if moon.flags & HANDLE_PROPAGATE:
                flag_handlers = ast.If(test=ast.Name('yloopsf'), body=[ast.Break()], orelse=[])
            else:
                flag_handlers = None
            if moon.flags & HANDLE_CONTINUE:
                orelse = [flag_handlers] if flag_handlers else []
                cnt_flag = 1 << (moon.loop_depth - 1) * 2
                flag_handlers = ast.If(test=ast.BinOp(op=ast.BitAnd(), left=ast.Name('yloopsf'), right=ast.Constant(cnt_flag)), body=[ast.Assign(targets=[ast.Name('yloopsf')], value=ast.Constant(0), lineno=1), ast.Continue()], orelse=orelse)
            if moon.flags & HANDLE_BREAK:
                orelse = [flag_handlers] if flag_handlers else []
                brk_flag = 2 << (moon.loop_depth - 1) * 2
                flag_handlers = ast.If(test=ast.BinOp(op=ast.BitAnd(), left=ast.Name('yloopsf'), right=ast.Constant(brk_flag)), body=[ast.Assign(targets=[ast.Name('yloopsf')], value=ast.Constant(0), lineno=1), ast.Break()], orelse=orelse)
            return flag_handlers
        with MoonGrabber() as grab:
            HANDLE_PROPAGATE = 1 << 0
            INDEXED = 1 << 1
            USES_I = 1 << 2
            RECOMPUTE_END = 1 << 3
            HANDLE_BREAK = 1 << 4
            HANDLE_CONTINUE = 1 << 5
            FAST_OREMPTY = 1 << 6
            NEEDS_YLOOPSF = 1 << 7
            NOT_INDEXED = 125
            DONT_RECOMPUTE_END = 119

            def moon_filter(moon, moonwalker):
                moon.flags = 0
                moon.loop_depth = 0
                if moon.node.__class__ in (ast.FunctionDef, ast.AsyncFunctionDef):
                    moon.kind = 'Fn'
                    moon.loopname = False
                    return moon
                if moon.node.__class__ in (ast.For, ast.While):
                    moon.kind = moon.node.__class__.__name__.lower()
                    moon.loopname = None
                    moon.loop_depth = 0
                    up = moon.up
                    yloopsf = 0
                    while up:
                        if up.node.__class__ in (ast.FunctionDef, ast.AsyncFunctionDef):
                            break
                        elif up.node.__class__ in (ast.For, ast.While) or (up.node.__class__ == ast.With and isinstance((what := up.node.items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'For')) or (up.node.__class__ == ast.With and isinstance((what := up.node.items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'While')):
                            moon.loop_depth += 1
                        up = up.up
                    moon.loop_depth = max(moon.loop_depth, moon.loop_depth)
                    grab(moon.up)
                    moon.node
                    return moon
                elif moon.node.__class__ == ast.With and isinstance((what := moon.node.items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'For'):
                    moon.kind = 'For'
                    if not call.args:
                        raise TransformError('For without iterable')
                    if not isinstance((name := what[0].optional_vars), ast.Name):
                        raise TransformError('For without as name')
                    if isinstance((_cmp := call.args[0]), ast.Compare):
                        if not len(_cmp.ops) == 1 or not isinstance(_cmp.ops[0], ast.In):
                            raise TransformError('For with weird compare')
                        if not isinstance(_cmp.left, (ast.Name, ast.Tuple)):
                            raise TransformError('For with weird name bind')
                        moon.iterator = _cmp.comparators[0]
                        moon.item_name = _cmp.left
                    else:
                        moon.iterator = _cmp
                        moon.item_name = None
                    if moon.iterator.__class__ in (ast.List, ast.ListComp, ast.Tuple):
                        moon.flags |= FAST_OREMPTY
                    moon.loopname = name.id
                    moon.orelse = []
                    moon.orempty = False
                    moon.istart = ast.Constant(value=0)
                    moon.flags |= RECOMPUTE_END
                    moon.end = None
                    yloopsf = 0
                    for (k, v) in ((kw.arg, kw.value) for kw in call.keywords):
                        ymatch_7_subject = k
                        if ymatch_7_subject == 'indexed':
                            if not isinstance(v, ast.Constant):
                                raise TransformError(f'{v} is not a constant')
                            if not isinstance(v.value, bool):
                                raise TransformError(f'{v.value} is not a boolean')
                            if v.value:
                                moon.flags |= INDEXED
                            else:
                                moon.flags &= NOT_INDEXED
                        elif ymatch_7_subject == 'start':
                            moon.istart = v
                        elif ymatch_7_subject == 'recompute_end':
                            if not isinstance(v, ast.Constant):
                                raise TransformError(f'{v} is not a constant')
                            if not isinstance(v.value, bool):
                                raise TransformError(f'{v.value} is not a boolean')
                            moon.flags |= INDEXED
                            if v.value:
                                moon.flags |= RECOMPUTE_END
                            else:
                                moon.flags &= DONT_RECOMPUTE_END
                        elif ymatch_7_subject == 'end':
                            if not isinstance(v, ast.Constant):
                                raise TransformError(f'{k}={v} is not a string')
                            _end = ast.parse(v.value).body[0]
                            if isinstance(_end, ast.Expr):
                                moon.end = [_end.value]
                            elif isinstance(_end, ast.Name):
                                moon.end = [_end]
                            else:
                                raise TransformError(f"don't know about {_end}")
                        elif True:
                            raise TransformError(f'what is {k}={v}?{_bfb_0a__}{ast.unparse(moon.node)}')
                    grab(moon.up)
                    moon.loop_depth = 0
                    up = moon.up
                    yloopsf = 0
                    while up:
                        if up.node.__class__ in (ast.FunctionDef, ast.AsyncFunctionDef):
                            break
                        elif up.node.__class__ in (ast.For, ast.While) or (up.node.__class__ == ast.With and isinstance((what := up.node.items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'For')) or (up.node.__class__ == ast.With and isinstance((what := up.node.items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'While')):
                            moon.loop_depth += 1
                        up = up.up
                    moon.loop_depth = max(moon.loop_depth, moon.loop_depth)
                    return moon
                elif moon.node.__class__ == ast.With and isinstance((what := moon.node.items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'While'):
                    moon.kind = 'While'
                    if not call.args:
                        raise TransformError('While without condition')
                    if not isinstance((name := what[0].optional_vars), ast.Name):
                        raise TransformError('While without as name')
                    yloopsf = 0
                    for (k, v) in ((kw.arg, kw.value) for kw in call.keywords):
                        ymatch_6_subject = k
                        if True:
                            raise TransformError(f'While got {k}')
                    moon.loopname = name.id
                    moon.orelse = []
                    moon.test_condition = call.args[0]
                    grab(moon.up)
                    moon.loop_depth = 0
                    up = moon.up
                    yloopsf = 0
                    while up:
                        if up.node.__class__ in (ast.FunctionDef, ast.AsyncFunctionDef):
                            break
                        elif up.node.__class__ in (ast.For, ast.While) or (up.node.__class__ == ast.With and isinstance((what := up.node.items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'For')) or (up.node.__class__ == ast.With and isinstance((what := up.node.items), list) and (len(what) == 1) and ((call := what[0].context_expr).__class__ == ast.Call) and (call.func.id == 'While')):
                            moon.loop_depth += 1
                        up = up.up
                    moon.loop_depth = max(moon.loop_depth, moon.loop_depth)
                    return moon
                elif isinstance(moon.node, ast.With) and isinstance((what := moon.node.items), list) and (len(what) == 1) and isinstance((attr := what[0].context_expr), ast.Attribute) and (attr.attr == 'orelse'):
                    moon.kind = 'orelse'
                    moon.loopname = attr.value.id
                    yloopsf = 0
                    for other in reversed(moonwalker.tree):
                        if other.kind in ('For', 'While') and other.loopname == moon.loopname:
                            moon.loop_moon = other
                            break
                    else:
                        raise TransformError('orelse without corresponding loop')
                    moon.loop_moon.orelse = moon.node.body
                    grab(moon.up)
                    return moon
                elif isinstance(moon.node, ast.With) and isinstance((what := moon.node.items), list) and (len(what) == 1) and isinstance((attr := what[0].context_expr), ast.Attribute) and (attr.attr == 'orempty'):
                    moon.kind = 'orempty'
                    moon.loopname = attr.value.id
                    yloopsf = 0
                    for other in reversed(moonwalker.tree):
                        if other.kind == 'For' and other.loopname == moon.loopname:
                            moon.loop_moon = other
                            break
                    else:
                        raise TransformError('orempty without corresponding loop')
                    moon.loop_moon.orempty = moon.node.body
                    grab(moon.up)
                    return moon
                elif isinstance(moon.node, ast.Attribute) and isinstance(moon.node.value, ast.Name) and (moon.node.attr in ('iter', 'it', 'item', 'i', 'index', 'Break', 'Continue')):
                    moon.kind = 'attr'
                    moon.loopname = moon.node.value.id
                    moon.loopattr = moon.node.attr
                    moon.loop_moon = None
                    moon.different_depth = False
                    yloopsf = 0
                    for other in reversed(moonwalker.tree):
                        if other.kind in ('Fn', 'For', 'While', 'for', 'while'):
                            if moon.loopattr in ('Break', 'Continue') and other.loop_depth == 0:
                                other.flags |= NEEDS_YLOOPSF
                            if other.loopname == moon.loopname:
                                if moon.loopattr in ('Break', 'Continue') and moon.different_depth:
                                    moon.different_depth.flags |= HANDLE_BREAK if moon.loopattr == 'Break' else HANDLE_CONTINUE
                                moon.loop_moon = other
                                break
                            elif moon.node in ast.walk(other.node):
                                if other.kind == 'Fn' and moon.loopname != 'ast' and (moon.loopattr in ('Break', 'Continue')):
                                    raise TransformError(f'{moon.loopname}.{moon.loopattr} outscoping a function')
                                if moon.different_depth:
                                    moon.different_depth.flags |= HANDLE_PROPAGATE
                                moon.different_depth = other
                    else:
                        return None
                    ymatch_5_subject = moon.loopattr
                    if (ymatch_5_subject == 'i' or ymatch_5_subject == 'index') and (not moon.loop_moon.flags & INDEXED):
                        moon.loop_moon.flags |= USES_I
                    elif (ymatch_5_subject == 'it' or ymatch_5_subject == 'item') and (not moon.loop_moon.flags & INDEXED and moon.up.node.__class__ == ast.Delete):
                        raise TransformError(f'think u forgot indexed `with For(..., indexed=True) as {moon.loopname}: {ast.unparse(moon.up.node)}`')
                    elif ymatch_5_subject == 'Break':
                        grab(moon.up.up)
                        grab(moon.up.node)
                    elif ymatch_5_subject == 'Continue':
                        grab(moon.up.up)
                        grab(moon.up.node)
                    grab(moon.up)
                    return moon
            yloopsf = 0
            for moon in MoonWalking(self.ast, filter_cb=moon_filter).tree:
                name = moon.loopname
                ymatch_4_subject = moon.kind
                if ymatch_4_subject == 'Fn':
                    ...
                elif ymatch_4_subject == 'for' or ymatch_4_subject == 'while':
                    moon.pop_extend([before_the_loop(moon), moon.node, after_the_loop(moon)], filternone=True)
                elif ymatch_4_subject == 'For' and moon.flags & INDEXED:
                    new_ast = [ast.Assign(targets=[ast.Name(f'_yfor_{name}_iter')], value=[moon.iterator], lineno=1)]
                    wcomparators = [ast.Call(func=ast.Name('len'), args=[ast.Name(f'_yfor_{name}_iter')], keywords=[])]
                    if not moon.flags & RECOMPUTE_END:
                        new_ast.append(ast.Assign(targets=[ast.Name(f'_yfor_{name}_end')], value=moon.end if moon.end else wcomparators[0], lineno=1))
                        wcomparators = [ast.Name(f'_yfor_{name}_end')]
                    if moon.orempty and (not moon.flags & FAST_OREMPTY):
                        new_ast.append(ast.Assign(targets=[ast.Name(f'_yfor_{name}_isempty')], value=ast.Constant(True), lineno=1))
                        moon.node.body.insert(0, ast.Assign(targets=[ast.Name(f'_yfor_{name}_isempty')], value=ast.Constant(False), lineno=1))
                    elif moon.orempty:
                        ...
                    wtest = ast.Compare(left=ast.Name(f'_yfor_{name}_i'), ops=[ast.Lt()], comparators=moon.end if moon.flags & RECOMPUTE_END and moon.end else wcomparators)
                    new_ast.extend([ast.Assign(targets=[ast.Name(f'_yfor_{name}_i')], value=moon.istart, lineno=1), before_the_loop(moon), (theloop := ast.While(test=wtest, body=moon.node.body + [ast.AugAssign(target=ast.Name(f'_yfor_{name}_i'), op=ast.Add(), value=ast.Constant(value=1)), ast.Assert(test=ast.Compare(left=ast.Name(f'_yfor_{name}_i'), ops=[ast.GtE()], comparators=[ast.Constant(value=0)]), msg=ast.Constant(value='u screwed up.. I mean, down, yep, up\nu screwed up!'))], orelse=moon.orelse)), after_the_loop(moon)])
                    if moon.item_name:
                        theloop.body.insert(0, ast.Assign(targets=[moon.item_name], value=ast.Subscript(value=ast.Name(f'_yfor_{name}_iter'), slice=ast.Name(f'_yfor_{name}_i')), lineno=1))
                    if moon.orempty and moon.flags & FAST_OREMPTY:
                        new_ast.append(ast.If(test=ast.UnaryOp(op=ast.Not(), operand=ast.Name(f'_yfor_{name}_iter')), body=moon.orempty, lineno=1))
                    moon.pop_extend(new_ast, filternone=True)
                elif ymatch_4_subject == 'For':
                    theloop = ast.For(target=ast.Tuple(elts=[ast.Name(f'_yfor_{name}_i'), ast.Name(f'_yfor_{name}_it')]) if moon.flags & USES_I else ast.Name(f'_yfor_{name}_it'), iter=ast.Call(func=ast.Name('enumerate'), args=[moon.iterator], keywords=[]) if moon.flags & USES_I else moon.iterator, body=moon.node.body, lineno=1, orelse=moon.orelse)
                    if moon.item_name:
                        theloop.body.insert(0, ast.Assign(targets=[moon.item_name], value=ast.Name(f'_yfor_{name}_it'), lineno=1))
                    if moon.orempty and (not moon.flags & FAST_OREMPTY):
                        theloop.body.insert(0, ast.Assign(targets=[ast.Name(f'_yfor_{name}_isempty')], value=ast.Constant(False), lineno=1))
                    if moon.orempty and moon.flags & FAST_OREMPTY:
                        theloop.iter = ast.NamedExpr(target=ast.Name(f'_yfor_{name}_iter'), value=theloop.iter)
                        moon.pop_extend([before_the_loop(moon), theloop, after_the_loop(moon), ast.If(test=ast.UnaryOp(op=ast.Not(), operand=ast.Name(f'_yfor_{name}_iter')), body=moon.orempty, lineno=1)], filternone=True)
                    elif moon.orempty:
                        moon.pop_extend([ast.Assign(targets=[ast.Name(f'_yfor_{name}_isempty')], value=ast.Constant(True), lineno=1), before_the_loop(moon), theloop, after_the_loop(moon)], filternone=True)
                    else:
                        moon.pop_extend([before_the_loop(moon), theloop, after_the_loop(moon)], filternone=True)
                elif ymatch_4_subject == 'orelse':
                    moon.pop()
                elif ymatch_4_subject == 'orempty' and moon.loop_moon.flags & FAST_OREMPTY:
                    moon.pop()
                elif ymatch_4_subject == 'orempty':
                    moon.replace(ast.If(test=ast.Name(f'_yfor_{moon.loopname}_isempty'), body=moon.node.body, orelse=[]))
                elif ymatch_4_subject == 'attr':
                    if moon.loopattr in ('Break', 'Continue'):
                        if moon.different_depth:
                            ymatch_3_subject = moon.loopattr
                            if ymatch_3_subject == 'Break':
                                flg = 2
                            elif ymatch_3_subject == 'Continue':
                                flg = 1
                            elif True:
                                raise NotImplementedError('new dev thing?')
                            assert moon.up.node.__class__ == ast.Expr, f'misplaced Break/Continue {moon.up.node.__class__}'
                            moon.up.pop_extend([ast.Assign(targets=[ast.Name('yloopsf')], value=ast.Constant(flg << moon.loop_moon.loop_depth * 2), lineno=1), ast.Break()])
                        else:
                            ymatch_2_subject = moon.loopattr
                            if ymatch_2_subject == 'Break':
                                moon.replace(ast.Break())
                            elif ymatch_2_subject == 'Continue':
                                moon.replace(ast.Continue())
                            elif True:
                                raise NotImplementedError('new dev thing?')
                    else:
                        if moon.loopattr == 'item':
                            moon.loopattr = 'it'
                        if moon.loopattr == 'index':
                            moon.loopattr = 'i'
                        if moon.loop_moon.flags & INDEXED and moon.loopattr == 'it':
                            moon.replace(ast.Subscript(value=ast.Name(f'_yfor_{moon.loopname}_iter'), slice=ast.Name(f'_yfor_{moon.loopname}_i')))
                        elif moon.loop_moon.kind == 'For':
                            moon.replace(ast.Name(f'_yfor_{moon.loopname}_{moon.loopattr}'))
                        else:
                            raise TransformError('TODO: why are we permessive only upon For?')
                elif ymatch_4_subject == 'While':
                    moon.pop_extend([before_the_loop(moon), (theloop := ast.While(test=moon.test_condition, body=moon.node.body, orelse=moon.orelse)), after_the_loop(moon)], filternone=True)
                elif True:
                    raise NotImplementedError(f'new kind {moon.kind}')
        del grab

        def moon_filter(moon):
            if moon.node.__class__ == ast.Call and (bind_fn_as := moon.node.func).__class__ == ast.Name and ((fname := bind_fn_as.id) in map(lambda p: ''.join(p), itertools.product(('emap', 'efilter', 'efiltermap'), ('', 'l', 'd', 's')))):
                moon.fname = fname
                yloopsf = 0
                for _yfor_ekwdloop_it in [v for (k, v) in emap(lambda kw: (kw.arg, kw.value), moon.node.keywords) if k == 'performance_required']:
                    v = _yfor_ekwdloop_it
                    assert isinstance(v, ast.Constant), v
                    moon.performance_required = v.value
                    
                    break
                else:
                    moon.performance_required = True
                if len((args := moon.node.args)) < 2:
                    raise TransformError(f"Where's my args? {ast.unparse(moon.node)}")
                moon.arg0 = args[0]
                moon.arg1 = args[1]
                if fname.startswith('efiltermap'):
                    if len(args) < 3:
                        raise TransformError('signature: efiltermap(filter_fn, map_fn, iterator)')
                    moon.arg2 = args[2]
                moon.up
                return moon
        for moon in MoonWalking(self.ast, filter_cb=moon_filter).tree:
            ymatch_1_subject = (moon.fname, type(moon.arg0), type(moon.arg1))
            if ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'emap' or ymatch_1_subject[0] == 'emapl' or ymatch_1_subject[0] == 'emaps') and (ymatch_1_subject[1] == ast.Lambda) and True:
                comp = ast.SetComp if moon.fname == 'emaps' else ast.ListComp
                moon.replace(comp(elt=moon.arg0.body, generators=[ast.comprehension(target=ast.Name(_args[0].arg) if len((_args := moon.arg0.args.args)) == 1 else ast.Tuple(elts=[ast.Name(_arg.arg) for _arg in _args]), iter=moon.arg1, is_async=False, ifs=[])]))
            elif (ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'emap' or ymatch_1_subject[0] == 'emapl' or ymatch_1_subject[0] == 'emaps') and True and True) and moon.performance_required:
                comp = ast.SetComp if moon.fname == 'emaps' else ast.ListComp
                moon.replace(comp(elt=ast.Call(func=moon.arg0, args=[ast.Name('aboba')], keywords=[]), generators=[ast.comprehension(target=ast.Name('aboba'), iter=moon.arg1, is_async=False, ifs=[])]))
            elif ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'emap' or ymatch_1_subject[0] == 'emapl' or ymatch_1_subject[0] == 'emaps') and True and True:
                moon.node.keywords = []
            elif ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'emapd') and (ymatch_1_subject[1] == ast.Lambda) and True:
                t = moon.arg0.body
                if not isinstance(t, ast.Tuple) or len(t.elts) != 2:
                    raise TransformError(f'{moon.fname}: lambda body not 2-tuple')
                moon.replace(ast.DictComp(key=t.elts[0], value=t.elts[1], generators=[ast.comprehension(target=ast.Tuple([ast.Name(_arg.arg) for _arg in moon.arg0.args.args]), iter=moon.arg1, is_async=False, ifs=[])]))
            elif (ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'emapd') and True and True) and moon.performance_required:
                raise TransformError(f'{moon.fname}: arg 1 should be lambda: 2-tuple{_bfb_0a__}try with performance_required=False{_bfb_0a__}{ast.unparse(moon.node)}')
            elif ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'emapd') and True and True:
                moon.node.keywords = []
            elif ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'efilter' or ymatch_1_subject[0] == 'efilters') and (ymatch_1_subject[1] == ast.Lambda) and True:
                comp = ast.SetComp if moon.fname == 'efilters' else ast.ListComp
                moon.replace(comp(elt=ast.Name(_args[0].arg) if len((_args := moon.arg0.args.args)) == 1 else ast.Tuple(elts=[ast.Name(_arg.arg) for _arg in _args]), generators=[ast.comprehension(target=ast.Name(_args[0].arg) if len((_args := moon.arg0.args.args)) == 1 else ast.Tuple(elts=[ast.Name(_arg.arg) for _arg in _args]), iter=moon.arg1, is_async=False, ifs=[moon.arg0.body])]))
            elif ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'efilter' or ymatch_1_subject[0] == 'efilters') and True and True:
                comp = ast.SetComp if moon.fname == 'efilters' else ast.ListComp
                moon.replace(comp(elt=ast.Name('aboba'), generators=[ast.comprehension(target=ast.Name('aboba'), iter=moon.arg1, is_async=False, ifs=[ast.Call(func=moon.arg0, args=[ast.Name('aboba')], keywords=[])])]))
            elif ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'efilterd') and (ymatch_1_subject[1] == ast.Lambda) and True:
                _args = [ast.Name(_a.arg) for _a in moon.arg0.args.args]
                moon.replace(ast.DictComp(key=_args[0], value=_args[1], generators=[ast.comprehension(target=ast.Tuple(elts=_args), iter=moon.arg1, is_async=False, ifs=[moon.arg0.body])]))
            elif ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'efilterd') and True and True:
                moon.replace(ast.DictComp(key=ast.Name('k'), value=ast.Name('v'), generators=[ast.comprehension(target=ast.Tuple(elts=[ast.Name('k'), ast.Name('v')]), iter=moon.arg1, is_async=False, ifs=[ast.Call(moon.arg0, args=[ast.Name('k'), ast.Name('v')], keywords=[])])]))
            elif ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'efiltermap' or ymatch_1_subject[0] == 'efiltermapl' or ymatch_1_subject[0] == 'efiltermaps') and (ymatch_1_subject[1] == ast.Lambda) and (ymatch_1_subject[2] == ast.Lambda):
                assert moon.arg0.args.args[0].arg == moon.arg1.args.args[0].arg, 'lambda args must be the same'
                comp = ast.SetComp if moon.fname == 'efiltermaps' else ast.ListComp
                moon.replace(comp(elt=moon.arg1.body, generators=[ast.comprehension(target=ast.Name(_args[0].arg) if len((_args := moon.arg0.args.args)) == 1 else ast.Tuple(elts=[ast.Name(_arg.arg) for _arg in _args]), iter=moon.arg2, is_async=False, ifs=[moon.arg0.body])]))
            elif ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'efiltermap' or ymatch_1_subject[0] == 'efiltermapl' or ymatch_1_subject[0] == 'efiltermaps') and (ymatch_1_subject[1] == ast.Lambda) and True:
                comp = ast.SetComp if moon.fname == 'efiltermaps' else ast.ListComp
                if len((_args := moon.arg0.args.args)) != 1:
                    raise TransformError(f'{moon.fname}: filter lambda must accept only one arg')
                arg = _args[0].arg
                moon.replace(comp(elt=ast.Call(func=moon.arg1, args=[ast.Name(arg)], keywords=[]), generators=[ast.comprehension(target=ast.Name(arg), iter=moon.arg2, is_async=False, ifs=[moon.arg0.body])]))
            elif ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'efiltermap' or ymatch_1_subject[0] == 'efiltermapl' or ymatch_1_subject[0] == 'efiltermaps') and True and (ymatch_1_subject[2] == ast.Lambda):
                comp = ast.SetComp if moon.fname == 'efiltermaps' else ast.ListComp
                if len((_args := moon.arg1.args.args)) != 1:
                    raise TransformError(f'{moon.fname}: map lambda must accept only one arg')
                arg = _args[0].arg
                moon.replace(comp(elt=moon.arg1.body, generators=[ast.comprehension(target=ast.Name(arg), iter=moon.arg2, is_async=False, ifs=[ast.Call(func=moon.arg0, args=[ast.Name(arg)], keywords=[])])]))
            elif ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'efiltermapd') and (ymatch_1_subject[1] == ast.Lambda) and (ymatch_1_subject[2] == ast.Lambda):
                _args = [ast.Name(_a.arg) for _a in moon.arg0.args.args]
                if [True for (n1, n2) in zip(_args, [ast.Name(_a.arg) for _a in moon.arg1.args.args]) if n1.id != n2.id]:
                    raise TransformError(f"{moon.fname}: lambda args doesn't match")
                moon.replace(ast.DictComp(key=moon.arg1.body.elts[0], value=moon.arg1.body.elts[1], generators=[ast.comprehension(target=ast.Tuple(elts=_args) if len(_args) != 1 else _args[0], iter=moon.arg2, is_async=False, ifs=[moon.arg0.body])]))
            elif ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'efiltermapd') and True and (ymatch_1_subject[2] == ast.Lambda):
                _args = [ast.Name(_a.arg) for _a in moon.arg1.args.args]
                moon.replace(ast.DictComp(key=moon.arg1.body.elts[0], value=moon.arg1.body.elts[1], generators=[ast.comprehension(target=ast.Tuple(elts=_args), iter=moon.arg2, is_async=False, ifs=[ast.Call(func=moon.arg0, keywords=[], args=_args)])]))
            elif (ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'efiltermapd') and (ymatch_1_subject[1] == ast.Lambda) and True) and moon.performance_required:
                raise TransformError(f'{moon.fname}: arg 1 should be lambda: 2-tuple{_bfb_0a__}try with performance_required=False{_bfb_0a__}{ast.unparse(moon.node)}')
            elif ymatch_as_seq(ymatch_1_subject) and 3 == len(ymatch_1_subject) and (ymatch_1_subject[0] == 'efiltermapd') and (ymatch_1_subject[1] == ast.Lambda) and True:
                moon.node.keywords = []
            elif True:
                raise NotImplementedError(f'{moon.fname}')
        if self.version_info < (3, 9):

            def grab_last_name(name, grab):
                for k in reversed(grab.defs):
                    if k[0] == name:
                        return bool(k[1])
            with MoonGrabber() as grab:
                grab.defs = []
                grab.done = []

                def moon_filter(moon):
                    if moon.node.__class__ == ast.AnnAssign and (tgt := moon.node.target).__class__ == ast.Name:
                        thing = 'ann' if moon.node.annotation.__class__ == ast.Name and moon.node.annotation.id in ('dict', 'Dict') or (moon.node.annotation.__class__ == ast.Subscript and moon.node.annotation.value.__class__ == ast.Name and (moon.node.annotation.value.id in ('dict', 'Dict'))) else False
                        grab.defs.append((tgt.id, thing))
                    elif moon.node.__class__ == ast.Assign:
                        if moon.node.value.__class__ == ast.Tuple and moon.node.targets[0].__class__ == ast.Tuple and (len(moon.node.value.elts) == len(moon.node.targets[0].elts)):
                            for (tgt, val) in zip(moon.node.targets[0].elts, moon.node.value.elts):
                                if tgt.__class__ == ast.Name:
                                    thing = 'assuc' if val.__class__ in (ast.Dict, ast.DictComp) or (val.__class__ == ast.Call and val.func.__class__ == ast.Name and (val.func.id == 'dict')) else False
                                    grab.defs.append((tgt.id, thing))
                        else:
                            for tgt in moon.node.targets:
                                if tgt.__class__ == ast.Name:
                                    thing = 'assus' if moon.node.value.__class__ in (ast.Dict, ast.DictComp) or (moon.node.value.__class__ == ast.Call and moon.node.value.func.__class__ == ast.Name and (moon.node.value.func.id == 'dict')) else False
                                    grab.defs.append((tgt.id, thing))
                    elif moon.node.__class__ == ast.arg and (known_dict := (moon.node.annotation.__class__ == ast.Name and moon.node.annotation.id in ('dict', 'Dict') or (moon.node.annotation.__class__ == ast.Subscript and moon.node.annotation.value.__class__ == ast.Name and (moon.node.annotation.value.id in ('dict', 'Dict'))))):
                        thing = 'arg' if known_dict else False
                        grab.defs.append((moon.node.arg, thing))
                    elif moon.node.__class__ == ast.BitOr:
                        if moon.up.node.__class__ == ast.BinOp and ((left := moon.up.node.left).__class__ == ast.Name and (grab_last_name(left.id, grab) or grab.defs[-1][0] == left.id) or left.__class__ in (ast.Dict, ast.DictComp) or (left.__class__ == ast.Call and left.func.__class__ == ast.Name and (left.func.id == 'dict'))) and ((right := moon.up.node.right).__class__ == ast.Name and grab_last_name(right.id, grab) or right.__class__ in (ast.Dict, ast.DictComp) or (right.__class__ == ast.Call and right.func.__class__ == ast.Name and (right.func.id == 'dict'))):
                            elts = (left, right)
                            nadir = moon.up
                            zenith = nadir.up
                            while zenith:
                                ymatch_0_subject = zenith.node.__class__
                                if ymatch_0_subject == ast.Assign:
                                    if zenith.node.value.__class__ == ast.Tuple and zenith.node.targets[0].__class__ == ast.Tuple and (len(zenith.node.value.elts) == len(zenith.node.targets[0].elts)):
                                        for (tgt, val) in zip(zenith.node.targets[0].elts, zenith.node.value.elts):
                                            if tgt.__class__ == ast.Name:
                                                thing = 'ASSbc'
                                                grab.defs.append((tgt.id, thing))
                                    else:
                                        for tgt in zenith.node.targets:
                                            if tgt.__class__ == ast.Name:
                                                thing = 'ASSbs'
                                                grab.defs.append((tgt.id, thing))
                                    break
                                elif (ymatch_0_subject == ast.AnnAssign or ymatch_0_subject == ast.AugAssign) and (tgt := zenith.node.target).__class__ == ast.Name:
                                    grab.defs.append((tgt.id, 'Ass'))
                                    break
                                elif ymatch_0_subject == ast.AnnAssign or ymatch_0_subject == ast.AugAssign:
                                    raise NotImplementedError(str(zenith))
                                elif ymatch_0_subject == ast.BinOp:
                                    if zenith.node.right.__class__ == ast.BinOp:
                                        breakpoint()
                                    elts = (*elts, zenith.node.right)
                                    nadir = zenith
                                    zenith = zenith.up
                                elif True:
                                    break
                            if elts[0].__class__ == ast.BinOp:
                                breakpoint()
                            grab(zenith)
                            nadir.elts = elts
                            return nadir
                        elif moon.up.node.__class__ == ast.AugAssign and ((left := moon.up.node.target).__class__ == ast.Name and grab_last_name(left.id, grab)):
                            if (right := moon.up.node.value).__class__ == ast.Name and grab_last_name(right.id, grab) or right.__class__ in (ast.Dict, ast.DictComp) or (right.__class__ == ast.Call and right.func.__class__ == ast.Name and (right.func.id == 'dict')):
                                moon.up.elts = (left, right)
                                grab(moon.up.up)
                                return moon.up
                            elif right.__class__ == ast.BinOp:

                                def aug_simplifier(left, right):
                                    """a |= b | c | d  -->  (a ((b c) d))
                            But I halready handled  (((a b) c) d)
                            """
                                    if right.__class__ == ast.BinOp:
                                        node = right
                                        flatten = []
                                        while node.__class__ == ast.BinOp:
                                            flatten.append(node.right)
                                            assert node.op.__class__ == ast.BitOr
                                            node = node.left
                                        flatten.append(node)
                                        result = ast.BinOp(left=..., op=ast.BitOr(), right=flatten[0])
                                        tmp = []
                                        for node in flatten[1:-1]:
                                            tmp.append(ast.BinOp(left=..., op=ast.BitOr(), right=node))
                                        tmp[-1].left = ast.BinOp(left=left, op=ast.BitOr(), right=flatten[-1])
                                        prev = tmp[-1]
                                        for tmp_ in reversed(tmp[:-1]):
                                            tmp_.left = prev
                                            prev = tmp_
                                        result.left = prev
                                        return result
                                if right.left.__class__ == ast.BinOp:
                                    simplified = aug_simplifier(left, right)
                                    fake_ass = ast.Assign(targets=[left], value=simplified, lineno=1)
                                else:
                                    fake_ass = ast.Assign(targets=[left], value=ast.BinOp(left=ast.BinOp(left=left, op=ast.BitOr(), right=right.left), op=ast.BitOr(), right=right.right), lineno=1)
                                new_moon = list(MoonWalking(fake_ass, filter_cb=moon_filter).tree)[0]
                                moon.up.elts = new_moon.elts
                                grab(moon.up.up)
                                return moon.up
                for moon in MoonWalking(self.ast, filter_cb=moon_filter).tree:
                    if moon.node in grab.done:
                        continue
                    grab.done.append(moon.node)
                    well = ast.Dict(keys=[None] * len(moon.elts), values=[*moon.elts])
                    if moon.node.__class__ == ast.AugAssign:
                        moon.replace(ast.Assign(targets=[moon.node.target], value=well, lineno=1))
                    elif moon.node.__class__ == ast.BinOp:
                        moon.replace(well)
                    else:
                        breakpoint()
            del grab
        for varname in sorted(backported_fstring):
            add_at_the_module_beginning(self.ast, ast.Assign(targets=[ast.Name(varname, context=ast.Store())], value=ast.Constant(chr(int(varname[len('_bfb_'):-2], 16))), lineno=1))
        if self.autoimport:
            add_at_the_module_beginning(self.ast, ast.Try(body=[ast.ImportFrom(module=f'yeastr.{self.autoimport}', names=[ast.alias(name='*')], level=0)], handlers=[ast.ExceptHandler(type=ast.Name('ImportError'), body=[ast.ImportFrom(module=self.autoimport, names=[ast.alias(name='*')], level=0)])], orelse=[], finalbody=[]))
        return ast.unparse(self.ast)



__all__ = ('emap', 'emapl', 'emapd', 'emaps', 'efilter', 'efilterl', 'efilterd', 'efilters', 'efiltermap', 'efiltermapl', 'efiltermapd', 'efiltermaps', 'TransformError', 'Moon', 'MoonWalking', 'MoonGrabber', 'Macros', '_macros', 'def_macro', 'mLang_conv', 'ymatch_as_seq', 'ymatch_as_map', 'ymatch_positional_origin', 'restricted_builtins', 'ast_copy', 'add_at_the_module_beginning', 'BuildTimeTransformer')
