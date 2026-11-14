import ast


class NameCounter(ast.NodeVisitor):
    def __init__(self):
        self.names = []

    def visit_Name(self, node):
        self.names.append(node.id)
        self.generic_visit(node)
