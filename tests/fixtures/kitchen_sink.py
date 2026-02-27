import math

FLAG = "module"


def make_counter(start):
    value = start

    def inc(step=1):
        nonlocal value
        value = value + step
        return value

    return inc


class Box:
    factor = 3

    def __init__(self, value):
        self.value = value

    def scaled(self):
        return self.value * self.factor


class TraceCtx:
    def __init__(self, trace):
        self.trace = trace

    def __enter__(self):
        self.trace.append("enter")
        return 7

    def __exit__(self, exc_type, exc, tb):
        self.trace.append("exit")
        return False


def counting(n):
    i = 0
    while i < n:
        yield i
        i = i + 1
    return "done"


def cascade(n):
    marker = yield from counting(n)
    yield marker


counter = make_counter(10)
counter_values = [counter(), counter(2), counter()]

trace = []
with TraceCtx(trace) as token:
    with_total = token + 5

pairs = [(i, j) for i in range(4) if i % 2 == 0 for j in range(3) if j > 0]
squares = {i: i * i for i in range(5) if i != 3}
unique_mod = {i % 3 for i in range(10)}
gen_values = list(i + 100 for i in range(4))

loop_total = 0
for n in range(6):
    if n == 1:
        continue
    if n == 5:
        break
    loop_total = loop_total + n

tmp = 99


def read_tmp():
    return tmp  # noqa: F821


del tmp
try:
    read_tmp()
except Exception as e:
    del_error = type(e).__name__

try:
    1 / 0
except Exception as e:
    exc_name = type(e).__name__
finally:
    final_flag = "finally"

RESULT = {
    "flag": FLAG,
    "sqrt": math.sqrt(81),
    "counter": counter_values,
    "box_scaled": Box(7).scaled(),
    "trace": trace,
    "with_total": with_total,
    "pairs": pairs,
    "squares": squares,
    "unique_mod": unique_mod,
    "gen_values": gen_values,
    "loop_total": loop_total,
    "del_error": del_error,
    "exc_name": exc_name,
    "final_flag": final_flag,
    "cascade": list(cascade(3)),
}
