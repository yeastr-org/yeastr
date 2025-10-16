"""Monkeypatching ast

- sort exception handlers

- always explicitly delimit tuples with parens

"""
import ast

# trick python 3.14 into defining ast._Unparser if it didn't already
ast.unparse(ast.Module(type_ignores=[], body=[]))

class _Unparser(ast._Unparser):
    @staticmethod
    def handler_sorter(handler):
        return (
            handler.type.id
            if isinstance(handler.type, ast.Name)
            else ast.unparse(handler)
        )

    def visit_Try(self, node):
        self.fill("try")
        with self.block():
            self.traverse(node.body)
        for ex in sorted(node.handlers, key=self.handler_sorter):
            self.traverse(ex)
        if node.orelse:
            self.fill("else")
            with self.block():
                self.traverse(node.orelse)
        if node.finalbody:
            self.fill("finally")
            with self.block():
                self.traverse(node.finalbody)

    def visit_Tuple(self, node):
        with self.delimit('(', ')'):
            self.items_view(self.traverse, node.elts)


ast._Unparser = _Unparser
