"""Run python -m yeastr.interactive

to get into the REPL
"""
# Important: add things to this module, as they will end up in the REPL's
# default globals.
import sys
import traceback

try:
    from yeastr.import_hooks import *
except ImportError:
    sys.path.insert(0, __file__.replace('interactive.py', ''))
    from import_hooks import *

try:
    import _pyrepl
    USE_PYREPL = 'stdlib'
except ImportError:
    try:
        import pyrepl
        USE_PYREPL = 'dep'
    except ImportError:
        USE_PYREPL = False

YEASTR_DEBUG = True
target_version = 'py38-none-any'

if __name__ == "__main__" and USE_PYREPL == 'stdlib':
    from _pyrepl.main import interactive_console as __pyrepl_interactive_console
    import _pyrepl.console
    class InteractiveColoredConsole(_pyrepl.console.InteractiveColoredConsole):
        def runsource(self, source, filename="<input>", symbol="single"):
            try:
                _yeastr_btt = BuildTimeTransformer(
                    source,
                    target_version,
                    autoimport=False,
                )
                source = _yeastr_btt.yang(_macros)
            except BaseException as exc:
                traceback.print_exception(exc)
                source = ''
            if YEASTR_DEBUG:
                print(source)
            super().runsource(source, filename=filename, symbol=symbol)
    _pyrepl.console.InteractiveColoredConsole = InteractiveColoredConsole
    __pyrepl_interactive_console()
elif __name__ == "__main__" and USE_PYREPL == 'dep':
    print('TODO: errr.... I didn\'t ever run this, does it work?')
    import pyrepl.python_reader
    class ReaderConsole(pyrepl.python_reader.ReaderConsole):
        def execute(self, text):
            try:
                _yeastr_btt = BuildTimeTransformer(
                    source,
                    target_version,
                )
                source = _yeastr_btt.yang(_macros)
            except BaseException as exc:
                traceback.print_exception(exc)
                source = ''
            super().execute(source)
    pyrepl.python_reader.ReaderConsole = ReaderConsole
    pyrepl.python_reader.main()
elif __name__ == "__main__" and not USE_PYREPL:
    raise NotImplementedError('you kinda need pyrepl')
