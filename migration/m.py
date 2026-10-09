# SPDX-License-Identifier: EUPL-1.2
"""Bounded parser for the common Power Query subset; preserves unsupported M intact."""
import re

TOKEN = re.compile(r'\s+|//[^\n]*|/\*|\*/|#"(?:[^"]|"")*"|"(?:[^"]|"")*"|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[A-Za-z_]\w*|=>|<>|<=|>=|[^\s]')
PRIORITY = {"or":1,"and":2,"=":3,"<>":3,"<":3,">":3,"<=":3,">=":3,"&":4,"+":5,"-":5,"*":6,"/":6}


def string(value):
    value = value[1:-1].replace('""', '"')
    def escape(match):
        names = {"cr":"\r","lf":"\n","tab":"\t","#":"#"}
        return "".join(names.get(part, chr(int(part,16)) if re.fullmatch(r"[0-9a-fA-F]{4,8}",part) else "#("+part+")") for part in match[1].split(","))
    return re.sub(r"#\(([^)]+)\)", escape, value)


class Parser:
    def __init__(self, source):
        if len(source) > 2 * 1024 * 1024: raise ValueError("M section exceeds 2 MiB parser limit")
        self.tokens, self.pos, self.depth = [], 0, 0
        comments = 0
        for match in TOKEN.finditer(source):
            value = match[0]
            if value == "/*": comments += 1
            elif value == "*/":
                if not comments: raise ValueError("Unexpected M comment terminator")
                comments -= 1
            elif comments or value.isspace() or value.startswith("//"): continue
            elif value.startswith('#"'): self.tokens.append(("quoted", string(value[1:])))
            elif value.startswith('"'): self.tokens.append(("string", string(value)))
            elif re.fullmatch(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", value): self.tokens.append(("number", value))
            else: self.tokens.append(("id" if re.fullmatch(r"[A-Za-z_]\w*",value) else "symbol", value))
            if comments > 64 or len(self.tokens) > 200_000: raise ValueError("M complexity limit exceeded")
        if comments: raise ValueError("Unclosed M comment")

    def peek(self): return self.tokens[self.pos][1] if self.pos < len(self.tokens) else None
    def pop(self):
        if self.pos >= len(self.tokens): raise ValueError("Truncated M expression")
        value = self.tokens[self.pos]; self.pos += 1; return value
    def require(self, value):
        if self.pop()[1] != value: raise ValueError("Expected M token " + value)

    def parse(self, minimum=0):
        self.depth += 1
        if self.depth > 128: raise ValueError("M nesting limit exceeded")
        try:
            kind, value = self.pop()
            if kind == "string": node = {"kind":"literal","value":value}
            elif kind == "quoted":node={"kind":"identifier","name":value}
            elif kind == "number": node = {"kind":"literal","value":float(value) if any(c in value for c in '.eE') else int(value)}
            elif value in ("true","false","null"): node = {"kind":"literal","value":{"true":True,"false":False,"null":None}[value]}
            elif value == "let":
                bindings = []
                while True:
                    name = self.pop()[1]; self.require("="); bindings.append([name,self.parse()])
                    if self.peek() != ",": break
                    self.pop()
                self.require("in"); node = {"kind":"let","bindings":bindings,"body":self.parse()}
            elif value == "each": node = {"kind":"lambda","body":self.parse()}
            elif value in ("not","-","+"): node = {"kind":"unary","op":value,"value":self.parse(3 if value == "not" else 7)}
            elif value == "type":
                typ = self.pop()[1]
                if typ == "nullable": typ = self.pop()[1]
                node = {"kind":"literal","value":"type:"+typ}
            elif value == "(":
                node = self.parse(); self.require(")")
            elif value == "{":
                values=[]
                if self.peek() != "}":
                    while True:
                        values.append(self.parse())
                        if self.peek() != ",": break
                        self.pop()
                self.require("}"); node = {"kind":"list","values":values}
            elif value == "[":
                name = self.pop()[1]
                if self.peek() == "=":
                    pairs=[]
                    while True:
                        self.require("="); pairs.append([name,self.parse()])
                        if self.peek() != ",": break
                        self.pop(); name=self.pop()[1]
                    self.require("]"); node = {"kind":"record","pairs":pairs}
                else:
                    self.require("]"); node = {"kind":"field","object":{"kind":"identifier","name":"_"},"name":name}
            elif kind == "id":
                name=value
                while self.peek() == ".": self.pop(); name += "." + self.pop()[1]
                node={"kind":"identifier","name":name}
            else: raise ValueError("Unsupported M token " + value)
            while True:
                next_value = self.peek()
                if next_value == "(":
                    self.pop(); args=[]
                    if self.peek() != ")":
                        while True:
                            args.append(self.parse())
                            if self.peek() != ",": break
                            self.pop()
                    self.require(")"); node={"kind":"call","function":node,"args":args}
                elif next_value == "[":
                    self.pop(); name=self.pop()[1]; self.require("]"); node={"kind":"field","object":node,"name":name}
                elif next_value in PRIORITY and PRIORITY[next_value] >= minimum:
                    operator=self.pop()[1]; node={"kind":"binary","op":operator,"left":node,"right":self.parse(PRIORITY[operator]+1)}
                else: break
            return node
        finally: self.depth -= 1

    def section(self):
        queries={}
        if self.peek() == "section":
            self.pop(); self.pop(); self.require(";")
        while self.peek() is not None:
            if self.peek() == "shared":
                self.pop(); name=self.pop()[1]; self.require("=")
                if name in queries:raise ValueError("Duplicate shared query: "+name)
                queries[name]=self.parse(); self.require(";")
            else:
                queries["Query"]=self.parse()
                if self.peek() == ";": self.pop()
                if self.peek() is not None: raise ValueError("Unsupported section declaration")
        return queries


def inventory(tree):
    calls, sources, steps = [], [], []
    def visit(node):
        if isinstance(node, dict):
            if node.get("kind") == "call" and node["function"].get("kind") == "identifier":
                name=node["function"]["name"]; calls.append(name)
                if name.split(".")[0] in ("File","Folder","Web","Sql","Odbc","OleDb","SharePoint","Excel"):
                    sources.append({"provider":name,"literal_arguments":[arg["value"] for arg in node["args"] if arg.get("kind")=="literal"]})
            if node.get("kind") == "let": steps.extend(name for name,_ in node["bindings"])
            for value in node.values(): visit(value)
        elif isinstance(node,list):
            for value in node: visit(value)
    visit(tree)
    return {"steps":steps,"functions":sorted(set(calls)),"sources":sources}
