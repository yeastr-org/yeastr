if __name__ == '__main__':
    import sys, ast
    import itertools
    import shutil
    import build
    sys.path.insert(0, __file__.rsplit('/', 1)[0] + '/yeastr')
    from bootstrapped import *

    # new_macros = Macros()

    PN = 'yeastr'
    PV = '0.0.2'

    for pep425 in (f'py{v}-none-any' for v in (
        #'39',
        #'310',
        #'311',
        #'312',
        #'313',
        '314',
        # but pls keep the oldest one as the last!
        '38',
    )):
        bootstrapped = 'yeastr/bootstrapped.py'

        # False means we only want the macros in there to be defined
        paths = (
            ('yeastr/shared.ypy', False),
            ('yeastr/yam.ypy', False),
            ('yeastr/utils.py', True),
            ('yeastr/minimal_runtime.py', True),
            ('yeastr/impl_macros.pyy', True),
            ('yeastr/impl_namedloops.pyy', False),
            ('yeastr/impl_call2comp.pyy', False),
            ('yeastr/backport_fstring_backslash.pyy', False),
            ('yeastr/backport_match.pyy', False),
            ('yeastr/backport_dict_ops.pyy', False),
            ('yeastr/build_time_transformer.pyy', True),
        )

        _all_ = _all = (
            *map(lambda p: ''.join(p),
                 itertools.product(('emap', 'efilter', 'efiltermap'),
                                   ('', 'l', 'd', 's'))),
            'TransformError',
            'Moon',
            'MoonWalking',
            'MoonGrabber',
            'Macros',
            '_macros',
            'def_macro',
            'mLang_conv',
            'ymatch_as_seq',
            'ymatch_as_map',
            'ymatch_positional_origin',
            # 'random_string',  # don't want to grab this name, rename it if you need it
            'restricted_builtins',
            'ast_copy',
            'add_at_the_module_beginning',
            'BuildTimeTransformer',
        )

        with open(bootstrapped + 'new', 'w') as out:
            for path, amalgamate in paths:
                with open(path, 'r') as in_:
                    out.write(f'# {
                            "Amalgamating" if amalgamate else "Getting macros"
                        } from {path}\n'
                    )
                    ying = BuildTimeTransformer(
                        in_.read(),
                        pep425,
                        autoimport=False,
                        strip_module_docstring=True,
                    )
                    if amalgamate:
                        out.write(ying.yang(_macros))
                        out.write('\n\n')
                    else:
                        ying.yang(_macros)
            out.write('\n\n')
            out.write(f'__all__ = {_all}\n')
        shutil.move(bootstrapped + 'new', bootstrapped)

        # ----------------------------------------------------------------------------
        # DECORATORS

        as_deco = 'yeastr/as_decorator.py'

        paths = (
            ('yeastr/utils.py', True),
            ('yeastr/minimal_runtime.py', True),
            ('yeastr/as_decorators.pyy', True),
        )
        _all = (
            *_all_,
            'with_namedloops', 'with_macros', 'with_call2comp',
            'backport_match', 'backport_fstring_backslash',
            'backport_dict_ops',
        )

        with open(as_deco + 'new', 'w') as out:
            for path, amalgamate in paths:
                with open(path, 'r') as in_:
                    out.write(f'# Amalgamating from {path}\n')
                    ying = BuildTimeTransformer(
                        in_.read(),
                        pep425,
                        autoimport=False,
                        strip_module_docstring=True,
                    )
                    if amalgamate:
                        out.write(ying.yang(_macros))
                        out.write('\n\n')
                    else:
                        ying.yang(_macros)
            out.write('\n\n')
            out.write(f'__all__ = {_all}\n')
        shutil.move(as_deco + 'new', as_deco)

        # ----------------------------------------------------------------------------
        # IMPORT HOOKS

        ihooks = 'yeastr/import_hooks.py'

        paths = (
            ('yeastr/import_hooks.pyy', True),
        )
        _all = (
            *_all_,
            'YeastrFileLoader',
            'YeastrPathFinder',
            'activate',
            'deactivate',
        )

        with open(ihooks + 'new', 'w') as out:
            for path, amalgamate in paths:
                with open(path, 'r') as in_:
                    ying = BuildTimeTransformer(
                        in_.read(),
                        pep425,
                        autoimport='bootstrapped',
                        strip_module_docstring=True,
                    )
                    if amalgamate:
                        out.write(ying.yang(_macros))
                        out.write('\n\n')
                    else:
                        ying.yang(_macros)
            out.write('\n\n')
            out.write(f'__all__ = {_all}\n')
        shutil.move(ihooks + 'new', ihooks)

        # ----------------------------------------------------------------------------
        # Simple Integrity test

        ptest = 'yeastr/packaging_test.py'

        paths = (
            ('yeastr/packaging_test.pyy', True),
        )
        _all = ('fn', )
        with open(ptest + 'new', 'w') as out:
            for path, amalgamate in paths:
                with open(path, 'r') as in_:
                    ying = BuildTimeTransformer(in_.read(), pep425, autoimport=False)
                    if amalgamate:
                        out.write(ying.yang(_macros))
                        out.write('\n\n')
                    else:
                        ying.yang(_macros)
            out.write('\n\n')
            out.write(f'__all__ = {_all}\n')
        shutil.move(ptest + 'new', ptest)

        # BUILD

        builder = build.ProjectBuilder('.')
        builder.build('sdist', 'dist')
        shutil.move(f'dist/{PN}-{PV}.tar.gz', f'dist/{PN}-{PV}-{pep425}.tar.gz')
        builder.build('wheel', 'dist')
        shutil.move(f'dist/{PN}-{PV}-py3-none-any.whl', f'dist/{PN}-{PV}-{pep425}.whl')

