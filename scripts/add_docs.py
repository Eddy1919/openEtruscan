import ast
import os
import sys


def process_file(filepath):
    with open(filepath, encoding="utf-8") as f:
        src = f.read()

    try:
        tree = ast.parse(src)
    except SyntaxError:
        return

    inserts = []

    # Track module doc
    if not ast.get_docstring(tree):
        inserts.append((0, '"""\nAutomatically added module documentation.\n"""\n'))

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if not ast.get_docstring(node):
                if node.body:
                    # Find exactly where the next line starts.
                    line_idx = node.body[0].lineno - 1
                    indent = " " * node.body[0].col_offset
                    prefix = (
                        "function/method"
                        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                        else "class"
                    )
                    doc = f'{indent}"""\n{indent}Automatically generated docstring for {node.name} {prefix}.\n{indent}"""\n'
                    inserts.append((line_idx, doc))

    if not inserts:
        return

    # Sort inserts descending so we can apply them without modifying earlier indices
    inserts.sort(key=lambda x: x[0], reverse=True)
    lines = src.split("\n")

    for idx, docstring in inserts:
        lines.insert(idx, docstring.rstrip("\n"))

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    # Default to the package source tree relative to this script.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(repo_root, "src")
    for dp, _dn, fns in os.walk(root_dir):
        for fn in fns:
            if fn.endswith(".py"):
                process_file(os.path.join(dp, fn))
