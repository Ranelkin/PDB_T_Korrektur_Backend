"""This Class specifies how to transform lark trees into dictionairies"""

from lark import Transformer

class TreeTransform(Transformer):

    def start(self, nodes):
        return nodes

    def definition(self, nodes):
        return {"definition": nodes[0], "value": nodes[1]}
    
    def domain(self, nodes):
        return {"domain": nodes[1], "value": nodes[2]}
    
    def extend(self, nodes):
        return {"grad": nodes[1], "value": nodes[2]}
    
    def complexity(self, nodes):
        return {"complexity": nodes[1:-1], "values": nodes[-1]}

    def tuple_expr(self, nodes):
        return {"tupel": nodes}

    def set_expr(self, nodes):
        return {"set": nodes}
    
    def power_expr(self, node):
        return {"^": node}

    def NAME(self, node):
        return str(node)
    
    def INT(self, node):
        return int(node)