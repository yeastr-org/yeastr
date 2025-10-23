_bfb_1b__ = '\x1b'
_bfb_0a__ = '\n'
_bfb_0001f40d__ = '🐍'

def fn():
    ymacro_str_ = 'abcdef'
    _str = [*ymacro_str_]
    del ymacro_str_
    yloopsf = 0
    while True:
        _yfor_chloop_iter = _str
        _yfor_chloop_i = 0
        while _yfor_chloop_i < len(_yfor_chloop_iter):
            ch = _yfor_chloop_iter[_yfor_chloop_i]
            ymatch_0_subject = ch
            if ymatch_0_subject == 'a' or ymatch_0_subject == 'b':
                _yfor_chloop_iter[_yfor_chloop_i] = 'c'
            elif True and all({x == 'c' for x in _yfor_chloop_iter}):
                yloopsf = 2
                break
            elif True and ch != 'c':
                del _yfor_chloop_iter[_yfor_chloop_i]
                _yfor_chloop_i -= 1
                if _yfor_chloop_i == len(_yfor_chloop_iter):
                    _yfor_chloop_i -= 1
            _yfor_chloop_i += 1
            assert _yfor_chloop_i >= 0, 'u screwed up.. I mean, down, yep, up\nu screwed up!'
        if yloopsf & 2:
            yloopsf = 0
            break
    return ''.join(_str) + '.de'
print('%s.%s' % ('media', fn()))
print(f"{f'{_bfb_1b__}[32m'}py{f'{_bfb_1b__}[39;49m'}{f'{_bfb_0a__}--' * 2}con {f'{_bfb_0001f40d__}'}")



__all__ = ('fn',)
