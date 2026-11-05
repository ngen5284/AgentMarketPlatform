import ast, operator

OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod
}

def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    elif isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_eval(node.left), _eval(node.right))
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand)
    raise ValueError('지원하지 않는 수식입니다.')

def run(task: str) -> str:
    cleaned = task.replace('계산해줘', '').replace('=', '').strip()
    try:
        res = _eval(ast.parse(cleaned, mode='eval'))
        return f'🧮 [계산 완료]\n수식: {cleaned}\n결과: {res}'
    except Exception as e:
        return f'계산 오류: {e}'
