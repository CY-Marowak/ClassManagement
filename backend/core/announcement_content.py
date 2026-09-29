from rest_framework import serializers

COLORS = {"#183b36", "#b42318", "#175cd3", "#267044"}
SIZES = {"14px", "16px", "20px"}
BLOCKS = {"paragraph", "bulletList", "orderedList"}


def validate_document(value):
    """Accept the editor's small document schema, never arbitrary HTML or CSS."""
    text_parts = []
    nodes = 0

    def invalid():
        raise serializers.ValidationError("公告格式不支援，請使用工具列的文字格式。")

    def visit(node, allowed, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 15000 or depth > 12 or not isinstance(node, dict):
            invalid()
        kind = node.get("type")
        if not isinstance(kind, str) or kind not in allowed:
            invalid()
        attrs = node.get("attrs", {})
        if not isinstance(attrs, dict):
            invalid()
        if kind == "orderedList":
            if set(attrs) - {"start", "type"} or attrs.get("type") is not None:
                invalid()
            start = attrs.get("start", 1)
            if type(start) is not int or not 1 <= start <= 9999:
                invalid()
        elif attrs:
            invalid()
        if kind == "text":
            if set(node) - {"type", "text", "marks"}:
                invalid()
            text = node.get("text")
            if not isinstance(text, str) or not text or "\x00" in text:
                invalid()
            text_parts.append(text)
            marks = node.get("marks", [])
            if not isinstance(marks, list) or len(marks) > 4:
                invalid()
            seen = set()
            for mark in marks:
                if not isinstance(mark, dict) or set(mark) - {"type", "attrs"}:
                    invalid()
                name = mark.get("type")
                if not isinstance(name, str) or name in seen:
                    invalid()
                seen.add(name)
                style = mark.get("attrs", {})
                if not isinstance(style, dict):
                    invalid()
                if name == "textStyle":
                    if set(style) - {"color", "fontSize"}:
                        invalid()
                    for attr, choices in [("color", COLORS), ("fontSize", SIZES)]:
                        value = style.get(attr)
                        if value is not None and (
                            not isinstance(value, str) or value not in choices
                        ):
                            invalid()
                elif name not in {"bold", "italic", "underline"} or style:
                    invalid()
            return
        if set(node) - {"type", "content", "attrs"}:
            invalid()
        children = node.get("content", [])
        if not isinstance(children, list):
            invalid()
        if kind == "hardBreak":
            if children:
                invalid()
            text_parts.append("\n")
            return
        if kind != "paragraph" and not children:
            invalid()
        if kind == "listItem" and (
            not isinstance(children[0], dict) or children[0].get("type") != "paragraph"
        ):
            invalid()
        child_types = (
            {"text", "hardBreak"}
            if kind == "paragraph"
            else ({"listItem"} if kind in {"bulletList", "orderedList"} else BLOCKS)
        )
        for child in children:
            visit(child, child_types, depth + 1)

    visit(value, {"doc"})
    text = "".join(text_parts)
    if not text.strip() or len(text) > 5000:
        raise serializers.ValidationError("內文需有 1～5000 字，格式不計字數。")
    return value
