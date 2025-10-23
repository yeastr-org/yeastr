try:
    from yeastr.bootstrapped import *
except ImportError:
    from bootstrapped import *
from importlib.machinery import FileFinder, PathFinder, SourceFileLoader
import sys

class YeastrFileLoader(SourceFileLoader):

    def cache_from_source(self, path):
        raise NotImplementedError('disables pyc cache')

    def _cache_bytecode(self, source_path, bytecode_path, data):
        raise NotImplementedError('disables pyc cache')

    @staticmethod
    def source_to_code(data, path, *, _optimize=-1):
        pep425 = 'py313-none-any'
        ying = BuildTimeTransformer(data.decode('utf-8'), pep425)
        source = ying.yang(_macros)
        return compile(source, path, 'exec', dont_inherit=True, optimize=_optimize)

class YeastrPathFinder(PathFinder):
    path_importer_cache = {}

    @classmethod
    def _path_importer_cache(cls, path):
        try:
            finder = cls.path_importer_cache[path]
        except KeyError:
            finder = FileFinder(path, (YeastrFileLoader, ['.ypy', '.ppy', 'pyy']))
            cls.path_importer_cache[path] = finder
        return finder

    @classmethod
    def invalidate_caches(cls):
        for finder in list(cls.path_importer_cache.values()):
            if hasattr(finder, 'invalidate_caches'):
                finder.invalidate_caches()

def activate():
    if YeastrPathFinder not in sys.meta_path:
        sys.meta_path.append(YeastrPathFinder)

def deactivate():
    if YeastrPathFinder in sys.meta_path:
        sys.meta_path.remove(YeastrPathFinder)
activate()



__all__ = ('emap', 'emapl', 'emapd', 'emaps', 'efilter', 'efilterl', 'efilterd', 'efilters', 'efiltermap', 'efiltermapl', 'efiltermapd', 'efiltermaps', 'TransformError', 'Moon', 'MoonWalking', 'MoonGrabber', 'Macros', '_macros', 'def_macro', 'mLang_conv', 'ymatch_as_seq', 'ymatch_as_map', 'ymatch_positional_origin', 'restricted_builtins', 'ast_copy', 'add_at_the_module_beginning', 'BuildTimeTransformer', 'YeastrFileLoader', 'YeastrPathFinder', 'activate', 'deactivate')
