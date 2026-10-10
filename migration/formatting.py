# SPDX-License-Identifier: EUPL-1.2
"""Explicit Excel-to-UNO/openpyxl formatting rules; unsupported values fail closed."""
PROPERTIES = {
    "font.bold": "CharWeight", "font.italic": "CharPosture",
    "font.name": "CharFontName", "font.size": "CharHeight", "font.color": "CharColor",
    "interior.color": "CellBackColor", "wraptext": "IsTextWrapped",
    "horizontalalignment": "HoriJustify", "verticalalignment": "VertJustify",
    "numberformat": "NumberFormat",
}
HORIZONTAL = {1: ("STANDARD", "general"), -4131: ("LEFT", "left"), -4108: ("CENTER", "center"), -4152: ("RIGHT", "right")}
VERTICAL = {-4160: (1, "top"), -4108: (2, "center"), -4107: (3, "bottom")}
CONSTANTS = {"xlleft": -4131, "xlcenter": -4108, "xlright": -4152, "xlgeneral": 1, "xltop": -4160, "xlbottom": -4107,
             "vbblack": 0, "vbred": 255, "vbgreen": 65280, "vbblue": 16711680, "vbyellow": 65535, "vbwhite": 16777215,
             "vbcyan": 16776960, "vbmagenta": 16711935}
CONSTANTS.update({"xlhalign" + name: value for name, value in (("left", -4131), ("center", -4108), ("right", -4152), ("general", 1))})
CONSTANTS.update({"xlvalign" + name: value for name, value in (("top", -4160), ("center", -4108), ("bottom", -4107))})
NUMBER_FORMATS = ("General", "0", "0.00", "#,##0", "#,##0.00", "0%", "0.00%", "@")
MANUAL_PROPERTIES = {"numberformatlocal", "borders", "style", "mergecells"}


def has_property(tokens):
    members = {prop.split(".")[0] for prop in PROPERTIES} | MANUAL_PROPERTIES
    return any(left == "." and right in members for left, right in zip(tokens, tokens[1:]))


def target(node):
    parts = []
    while node.get("kind") == "member":
        parts.insert(0, node["name"])
        node = node["object"]
        if parts[0] in MANUAL_PROPERTIES:
            raise NotImplementedError("Formatting property " + ".".join(parts) + " requires manual migration")
        if parts[0] in ("font", "interior") or ".".join(parts) in PROPERTIES:
            prop = ".".join(parts)
            if prop not in PROPERTIES:
                raise NotImplementedError("Formatting property " + prop + " requires manual migration")
            return node, prop
    return None


def rgb(red, green, blue):
    if any(type(value) is not int or not 0 <= value <= 255 for value in (red, green, blue)):
        raise NotImplementedError("RGB requires integer components from 0 to 255")
    return red + green * 256 + blue * 65536


def validate(prop, value):
    if prop not in PROPERTIES:
        raise NotImplementedError("Unsupported formatting property: " + prop)
    if prop in ("font.bold", "font.italic", "wraptext"):
        if type(value) not in (bool, int) or value not in (False, True, -1):
            raise NotImplementedError("Boolean formatting requires True/False or 0/1/-1")
        return bool(value)
    if prop.endswith(".color"):
        if type(value) is not int or not 0 <= value <= 0xFFFFFF:
            raise NotImplementedError("Only explicit RGB colours are supported; theme/system colours require review")
        # Excel stores 0xBBGGRR; UNO and openpyxl use 0xRRGGBB.
        return ((value & 255) << 16) | (value & 65280) | (value >> 16)
    if prop == "font.name":
        if not isinstance(value, str) or not value or len(value) > 255:
            raise NotImplementedError("Font name must be a nonempty string of at most 255 characters")
    elif prop == "font.size":
        if type(value) not in (int, float) or not 0 < value <= 409:
            raise NotImplementedError("Font size must be greater than zero and at most 409 points")
    elif prop == "numberformat":
        if value not in NUMBER_FORMATS:
            raise NotImplementedError("Number format requires manual migration: " + str(value))
    elif prop in ("horizontalalignment", "verticalalignment"):
        if type(value) is not int or value not in (HORIZONTAL if prop == "horizontalalignment" else VERTICAL):
            raise NotImplementedError("Alignment requires a supported Excel alignment constant")
    return value


def check_expression(prop, node):
    """Reject unsupported constant values before producing a candidate."""
    def constant(value):
        kind = value["kind"]
        if kind == "literal": return value["value"]
        if kind == "number": return float(value["value"]) if any(c in value["value"] for c in ".e") else int(value["value"])
        if kind == "identifier":
            return {**CONSTANTS, "true": True, "false": False}[value["name"]]
        if kind == "unary" and value["op"] in ("+", "-"):
            return constant(value["value"]) * (-1 if value["op"] == "-" else 1)
        raise KeyError("Dynamic value")
    try: value = constant(node)
    except KeyError: return
    validate(prop, value)


def basic_helpers():
    cases = []
    for prop, member in PROPERTIES.items():
        checks, expression = [], "value"
        if prop in ("font.bold", "font.italic", "wraptext"):
            checks = ['If VarType(value) <> 11 And value <> 0 And value <> 1 And value <> -1 Then Err.Raise 5, "Cellwright", "Boolean formatting requires True/False"']
            expression = 'CBool(value)'
            if prop == "font.bold": expression = 'IIf(CBool(value), 150, 100)'
            if prop == "font.italic": expression = 'IIf(CBool(value), com.sun.star.awt.FontSlant.ITALIC, com.sun.star.awt.FontSlant.NONE)'
        elif prop.endswith(".color"):
            checks = ['If value < 0 Or value > 16777215 Or value <> Fix(value) Then Err.Raise 5, "Cellwright", "Only explicit RGB colours are supported"']
            expression = '((CLng(value) And 255) * 65536) + (CLng(value) And 65280) + (CLng(value) \\ 65536)'
        elif prop == "font.size": checks = ['If value <= 0 Or value > 409 Then Err.Raise 5, "Cellwright", "Font size outside supported range"']
        elif prop == "font.name": checks = ['If VarType(value) <> 8 Or Len(value) = 0 Or Len(value) > 255 Then Err.Raise 5, "Cellwright", "Invalid font name"']
        elif prop in ("horizontalalignment", "verticalalignment"):
            values = HORIZONTAL if prop == "horizontalalignment" else VERTICAL
            checks = ['Select Case value'] + [f'Case {key}: value = ' + ('com.sun.star.table.CellHoriJustify.' + entry[0] if prop == "horizontalalignment" else str(entry[0])) for key, entry in values.items()] + ['Case Else: Err.Raise 5, "Cellwright", "Unsupported alignment"', 'End Select']
        elif prop == "numberformat":
            checks = ['Select Case value', 'Case ' + ', '.join('"' + code + '"' for code in NUMBER_FORMATS), 'Case Else: Err.Raise 5, "Cellwright", "Number format requires manual migration"', 'End Select', 'Dim locale As Object, key As Long', 'locale = CreateUnoStruct("com.sun.star.lang.Locale")', 'locale.Language = "en": locale.Country = "US"', 'key = ThisComponent.NumberFormats.queryKey(value, locale, True)', 'If key < 0 Then key = ThisComponent.NumberFormats.addNew(value, locale)']
            expression = 'key'
        cases.append('Case "' + prop + '"\n' + '\n'.join(checks + ['target.' + member + ' = ' + expression]))
    return '''
Function MFFormatRange(sheetName As String, address As String) As Object
    MFFormatRange = ThisComponent.Sheets.getByName(sheetName).getCellRangeByName(address)
End Function
Function MFVbaRGB(red As Variant, green As Variant, blue As Variant) As Long
    If Not IsNumeric(red) Or Not IsNumeric(green) Or Not IsNumeric(blue) Then Err.Raise 5, "Cellwright", "RGB requires numeric components"
    If red <> Fix(red) Or green <> Fix(green) Or blue <> Fix(blue) Then Err.Raise 5, "Cellwright", "RGB requires integer components"
    If red < 0 Or red > 255 Or green < 0 Or green > 255 Or blue < 0 Or blue > 255 Then Err.Raise 5, "Cellwright", "RGB components outside supported range"
    MFVbaRGB = red + green * 256 + blue * 65536
End Function
Sub MFFormat(target As Object, prop As String, value As Variant)
    Dim bounds
    bounds = target.getRangeAddress()
    If (CDbl(bounds.EndRow) - bounds.StartRow + 1) * (CDbl(bounds.EndColumn) - bounds.StartColumn + 1) > 100000 Then Err.Raise 5, "Cellwright", "Formatting exceeds 100,000 cells"
    Select Case prop
''' + '\n'.join(cases) + '''
    Case Else: Err.Raise 5, "Cellwright", "Unsupported formatting property"
    End Select
End Sub
'''
