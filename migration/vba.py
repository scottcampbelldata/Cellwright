# SPDX-License-Identifier: EUPL-1.2
"""Tolerant VBA syntax tree and deterministic Python generation for the supported subset.

Unsupported statements retain their source and generate a failing TODO, never a no-op.
"""
import json
import re
import builtins
import keyword
from migration import formatting


class Unsupported(ValueError):
    pass


TOKEN = re.compile(r'\s*("(?:[^"]|"")*"|&[Hh][0-9A-Fa-f]+|\d+(?:\.\d*)?(?:[Ee][+-]?\d+)?|[A-Za-z_][\w]*\$?|<=|>=|<>|:=|[^\s])')
OPERATORS = {"or": (1, "or"), "and": (2, "and"), "=": (3, "=="), "<>": (3, "!="), "<": (3, "<"), ">": (3, ">"), "<=": (3, "<="), ">=": (3, ">="), "&": (4, "concat"), "+": (5, "+"), "-": (5, "-"), "*": (6, "*"), "/": (6, "/"), "\\": (6, "idiv"), "mod": (6, "mod"), "^": (7, "**")}
BUILTINS = {"abs", "len", "cstr", "cint", "clng", "cdbl", "val", "isnumeric", "ucase", "lcase", "trim", "ltrim", "rtrim", "left", "right", "mid", "replace", "instr", "int", "fix", "round", "sqr", "chr", "asc", "iif", "array", "lbound", "ubound", "split", "join", "year", "month", "day", "date", "now", "weekday", "dateadd"}
CONSTANTS = {"true": "True", "false": "False", "nothing": "None", "empty": "None", "vbcrlf": "'\\r\\n'", "vblf": "'\\n'", "vbtab": "'\\t'", "vbnullstring": "''"}
BUILTINS.add("rgb")
CONSTANTS.update({name: str(value) for name, value in formatting.CONSTANTS.items()})

def safe_name(name):
    reserved = set(dir(builtins)) | {"configure", "_vb"}
    environment = {"range", "cells", "worksheets", "sheets", "application", "activesheet", "thisworkbook", "activeworkbook", "worksheetfunction"}
    return "_mf_" + name if (name in reserved or keyword.iskeyword(name)) and name not in environment else name


def tokens(text):
    return [value if value.startswith('"') else value.lower().rstrip("$") for value in TOKEN.findall(text)]


class Expression:
    def __init__(self, text):
        if len(text)>65536:raise Unsupported("Expression exceeds 64 KiB")
        self.values = tokens(text)
        self.pos = 0

    def pop(self):
        if self.pos >= len(self.values):
            raise Unsupported("Incomplete expression")
        value = self.values[self.pos]
        self.pos += 1
        return value

    def peek(self):
        return self.values[self.pos] if self.pos < len(self.values) else None

    def parse(self, minimum=0, depth=0):
        if depth>120:raise Unsupported("Expression nesting limit exceeded")
        value = self.pop()
        if value in ("-", "+", "not"):
            node = {"kind": "unary", "op": value, "value": self.parse(3 if value == "not" else 7,depth+1)}
        elif value == "(":
            node = self.parse(depth=depth+1)
            if self.pop() != ")":
                raise Unsupported("Unclosed parentheses")
        elif value.startswith('"'):
            node = {"kind": "literal", "value": value[1:-1].replace('""', '"')}
        elif re.fullmatch(r"&h[0-9a-f]+|\d+(?:\.\d*)?(?:e[+-]?\d+)?", value):
            node = {"kind": "number", "value": str(int(value[2:], 16)) if value.startswith("&h") else value}
        elif re.fullmatch(r"[a-z_]\w*", value):
            node = {"kind": "identifier", "name": value}
        else:
            raise Unsupported(f"Unsupported expression token {value}")
        while True:
            next_value = self.peek()
            if next_value == ".":
                self.pop()
                member = self.pop()
                if not re.fullmatch(r"[a-z_]\w*", member):
                    raise Unsupported("Invalid member")
                node = {"kind": "member", "object": node, "name": member}
            elif next_value == "(":
                self.pop()
                args = []
                if self.peek() != ")":
                    while True:
                        args.append(self.parse(depth=depth+1))
                        if self.peek() != ",":
                            break
                        self.pop()
                if self.pop() != ")":
                    raise Unsupported("Unclosed call")
                node = {"kind": "call", "object": node, "args": args}
            elif next_value in OPERATORS and OPERATORS[next_value][0] >= minimum:
                op = self.pop()
                priority = OPERATORS[op][0]
                node = {"kind": "binary", "op": op, "left": node, "right": self.parse(priority if op == "^" else priority + 1,depth+1)}
            else:
                break
        return node


def expression(text):
    parser = Expression(text)
    node = parser.parse()
    if parser.peek() is not None:
        raise Unsupported("Unsupported expression suffix " + str(parser.peek()))
    return node


def emit(node, callee=False):
    kind = node["kind"]
    if kind == "literal":
        return repr(node["value"])
    if kind == "number":
        return node["value"]
    if kind == "identifier":
        name = node["name"]
        if name in CONSTANTS:
            return CONSTANTS[name]
        if name in ("date", "now") and not callee:return "_vb." + name + "()"
        return "_vb." + name if name in BUILTINS else safe_name(name)
    if kind == "member":
        if formatting.target(node): raise Unsupported("Reading formatting properties requires manual migration")
        if node["name"].startswith("_"): raise Unsupported("Private Python attributes are not VBA members")
        if node["object"].get("name") == "vba" and node["name"] in BUILTINS:
            return "_vb." + node["name"] + ("()" if node["name"] in ("date", "now") and not callee else "")
        return emit(node["object"]) + "." + node["name"]
    if kind == "call":
        return emit(node["object"], callee=True) + "(" + ", ".join(emit(a) for a in node["args"]) + ")"
    if kind == "unary":
        if node["op"] == "not": return "_vb.not_(" + emit(node["value"]) + ")"
        return "(" + node["op"] + " " + emit(node["value"]) + ")"
    left, right = emit(node["left"]), emit(node["right"])
    op = OPERATORS[node["op"]][1]
    if op in ("and", "or"): return f"_vb.{op}_({left}, {right})"
    if op in ("concat", "idiv", "mod"):
        return f"_vb.{op}({left}, {right})"
    return f"({left} {op} {right})"


def split_statements(source):
    """Remove comments and join continued lines without changing string literals."""
    pending, first = "", 1
    for line_number, line in enumerate(source.replace("\r\n", "\n").replace("\r", "\n").splitlines(), 1):
        parts, current, quoted, i = [], "", False, 0
        while i < len(line):
            char = line[i]
            if char == '"':
                if quoted and i + 1 < len(line) and line[i + 1] == '"':
                    current += '""'
                    i += 2
                    continue
                quoted = not quoted
            if not quoted and char == "'":
                break
            if not quoted and char == ":" and (i + 1 == len(line) or line[i + 1] != "="):
                parts.append(current)
                current = ""
            else:
                current += char
            i += 1
        parts.append(current)
        for part in parts:
            part = part.strip()
            if not part or re.match(r"(?i)^rem(?:\s|$)", part):
                continue
            if not pending:
                first = line_number
            if part.endswith(" _"):
                pending += part[:-2] + " "
            else:
                yield first, pending + part
                pending = ""
    if pending:
        yield first, pending


def syntax(source):
    nodes = []
    for line, text in split_statements(source):
        lower = text.lower()
        node = {"line": line, "source": text}
        procedure = re.fullmatch(r"(?i)(?:(?:public|private|friend|static)\s+)?(sub|function)\s+(\w+)\s*\((.*?)\)(?:\s+as\s+\w+)?", text)
        if procedure:
            node.update(kind="procedure", procedure_kind=procedure[1].lower(), name=procedure[2].lower(), parameters=procedure[3])
        elif re.match(r"(?i)^(attribute|option)\b", text):
            node.update(kind="metadata")
        elif lower in ("end sub", "end function", "end if", "else", "wend", "end with", "loop") or lower.startswith("next"):
            node.update(kind="boundary", boundary=lower)
        else:
            node.update(kind="statement")
        nodes.append(node)
    return nodes


def assignment(text):
    parts, nesting = tokens(re.sub(r"(?i)^(set|let)\s+", "", text)), 0
    for i, token in enumerate(parts):
        nesting += (token == "(") - (token == ")")
        if token == "=" and nesting == 0:
            return expression(" ".join(parts[:i])), expression(" ".join(parts[i + 1:]))
    return None


def to_python(source):
    nodes = syntax(source)
    output = ["# Generated by MacroFerry; review TODOs and verify against Excel.", "from migration import runtime as _vb", "", "def configure(book):", "    globals().update(book.environment())", ""]
    todos, procedures, rewrites = [], [], []
    depth, procedure, function, blocks = 0, None, False, []

    def write(text):
        output.append("    " * depth + text)

    for node in nodes:
        text, lower = node["source"], node["source"].lower()
        try:
            if node["kind"] == "metadata":
                if lower.startswith("option") and lower not in ("option explicit", "option base 0", "option compare binary"):
                    raise Unsupported("Option changes require manual semantic review")
                continue
            if node["kind"] == "procedure":
                if node['name'] in BUILTINS or node['name'] in CONSTANTS:raise Unsupported("Procedure shadows a language intrinsic")
                if procedure:
                    raise Unsupported("Nested or unclosed procedure")
                params = []
                for p in node["parameters"].split(","):
                    if not p.strip():
                        continue
                    match = re.fullmatch(r"(?i)\s*byval\s+(\w+)(?:\s+as\s+\w+)?\s*", p)
                    if not match:
                        raise Unsupported("ByRef, optional or array parameters require review")
                    if match[1].lower() in BUILTINS or match[1].lower() in CONSTANTS:raise Unsupported("Parameter shadows a language intrinsic")
                    params.append(safe_name(match[1].lower()))
                procedure, function = node["name"], node["procedure_kind"] == "function"
                procedures.append(procedure)
                output.extend(["", f"def {safe_name(procedure)}({', '.join(params)}):"])
                depth = 1
                write("_result = None" if function else "pass")
                continue
            if not procedure:
                raise Unsupported("Module-level declarations or class state require review")
            if lower in ("end sub", "end function"):
                if blocks:
                    raise Unsupported("Unclosed control block")
                if function:
                    write("return _result")
                depth, procedure = 0, None
            elif lower == "end if" or lower == "wend" or lower.startswith("next") or lower == "end with":
                expected = "if" if lower == "end if" else "while" if lower == "wend" else "with" if lower == "end with" else "for"
                if not blocks or blocks.pop()[0] != expected:
                    raise Unsupported("Mismatched control block")
                depth -= 1
            elif lower == "else" or lower.startswith("elseif "):
                if not blocks or blocks[-1][0] != "if":
                    raise Unsupported("Else without If")
                depth -= 1
                write("else:" if lower == "else" else "elif " + emit(expression(text[7:-4].strip())) + ":")
                depth += 1
                write("pass")
            elif match := re.fullmatch(r"(?is)if\s+(.*?)\s+then\s*", text):
                write("if " + emit(expression(match[1])) + ":")
                blocks.append(("if", None))
                depth += 1
                write("pass")
            elif match := re.fullmatch(r"(?i)for\s+(\w+)\s*=\s*(.*?)\s+to\s+(.*?)(?:\s+step\s+(.*))?", text):
                write(f"for {safe_name(match[1].lower())} in _vb.for_range({emit(expression(match[2]))}, {emit(expression(match[3]))}, {emit(expression(match[4] or '1'))}):")
                blocks.append(("for", None))
                depth += 1
                write("pass")
            elif match := re.fullmatch(r"(?i)for\s+each\s+(\w+)\s+in\s+(.+)", text):
                write(f"for {safe_name(match[1].lower())} in {emit(expression(match[2]))}:")
                blocks.append(("for", None))
                depth += 1
                write("pass")
            elif lower.startswith("while "):
                write("while " + emit(expression(text[6:])) + ":")
                blocks.append(("while", None))
                depth += 1
                write("pass")
            elif lower.startswith("with "):
                variable = "_with_" + str(node["line"])
                value = text[5:]
                if value.startswith("."):
                    context = next((v for k, v in reversed(blocks) if k == "with"), None)
                    if not context: raise Unsupported("Member outside With")
                    value = context + value
                root = expression(value)
                if root["kind"] == "member" and root["name"] in ("font", "interior"):
                    variable = value
                else:
                    write(variable + " = " + emit(root))
                write("if True:")
                blocks.append(("with", variable))
                depth += 1
            elif re.match(r"(?i)^(dim|static)\b", text):
                for declaration in text.split(None, 1)[1].split(","):
                    match = re.fullmatch(r"(?i)\s*(\w+)(?:\s+as\s+(\w+))?\s*", declaration)
                    if not match:
                        raise Unsupported("Array or object declaration requires review")
                    if match[1].lower() in BUILTINS or match[1].lower() in CONSTANTS:raise Unsupported("Declaration shadows a language intrinsic")
                    typ = (match[2] or "variant").lower()
                    initial = "''" if typ == "string" else "False" if typ == "boolean" else "0" if typ in ("integer", "long", "double", "single", "currency", "byte") else "None"
                    write(safe_name(match[1].lower()) + " = " + initial)
            elif lower in ("exit sub", "exit function"):
                write("return _result" if function else "return")
            elif lower in ("exit for", "exit do"):
                write("break")
            else:
                if text.startswith("."):
                    context = next((v for k, v in reversed(blocks) if k == "with"), None)
                    if not context:
                        raise Unsupported("Member outside With")
                    text = context + text
                pair = assignment(text)
                if pair is not None:
                    lhs, rhs = pair
                    if lhs["kind"] not in ("identifier", "member"):
                        raise Unsupported("Indexed assignment requires review")
                    formatted = formatting.target(lhs)
                    if formatted:
                        root, prop = formatted
                        formatting.check_expression(prop, rhs)
                        replacement = f"_vb.format_range({emit(root)}, {prop!r}, {emit(rhs)})"
                        write(replacement)
                        rewrites.append({"line": node["line"], "rule_id": "FORMAT-" + prop.upper().replace(".", "-"), "before": node["source"], "after": replacement})
                        continue
                    target = emit(lhs)
                    if lhs.get("name") == procedure:
                        target = "_result"
                    write(target + " = " + emit(rhs))
                else:
                    text = re.sub(r"(?i)^call\s+", "", text)
                    try:
                        call = expression(text)
                    except Unsupported:
                        match = re.fullmatch(r"([\w.]+)\s+(.+)", text)
                        if not match:
                            raise
                        call = expression(match[1] + "(" + match[2] + ")")
                    if call["kind"] != "call":
                        call = {"kind": "call", "object": call, "args": []}
                    write(emit(call))
        except (Unsupported, NotImplementedError, IndexError, RecursionError) as error:
            reason = f"line {node['line']}: {error}"
            todos.append({"line": node["line"], "source": node["source"], "reason": str(error)})
            write("# MACROFERRY TODO: " + node["source"].replace("\n", " "))
            write("raise NotImplementedError(" + repr(reason) + ")")
    if procedure or blocks:
        todos.append({"line": len(source.splitlines()), "source": "", "reason": "Unclosed procedure or control block"})
        write("raise NotImplementedError('Unclosed VBA block')")
    generated = "\n".join(output) + "\n"
    try:
        compile(generated, "<converted>", "exec")
    except SyntaxError as error:
        todos.append({"line": error.lineno, "source": "", "reason": "Generated syntax requires review"})
        generated = "# Original VBA retained in the adjacent source file.\nraise NotImplementedError('VBA structure requires manual conversion')\n"
    return {"source": generated, "todos": todos, "rewrites": rewrites, "procedures": procedures, "syntax": nodes}
