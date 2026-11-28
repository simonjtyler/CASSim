"""The TI-Nspire CX CAS menus and dialogs as data (FR-DEV-001, FR-DEV-007, FR-CALC-005).

Checked against the Teacher Software on 2026-11-08 (`docs/testing/emulator-menus-results.md`):
every menu lists the device's items in the device's order with its numbers, so `menu 3 1` is Solve
and `menu 5 5 2` is Normal Cdf… as on the handheld. Items CASSim cannot do yet are greyed
placeholders (`todo`) in their real places; a placeholder submenu still opens and shows the device's
items, all greyed. A label ending in `…` opens a dialog (a `Wizard`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace

from cassim.core.compat import finance as fin
from cassim.device.keys import Action, Binding
from cassim.device.menu import MenuItem
from cassim.device.wizard import Field, Wizard
from cassim.devices.nspire import sheet_inference
from cassim.devices.nspire.pages.spreadsheet import STAT_CALCULATIONS
from cassim.devices.nspire.statistics import INTERVALS, TESTS, command_wizard
from cassim.devices.nspire.syntax import COMMANDS, CONVERSIONS, FUNCTIONS

NOT_YET = "Not in CASSim yet"
STUB_PAGE = "Adds a placeholder: this page type is not built yet"


def fn(label: str, name: str, key: str = "") -> MenuItem:
    """A leaf that types `name(`, with its syntax hint (`√` is the root template)."""
    if name == "√":
        return MenuItem(label, "template", "root", key=key, hint=FUNCTIONS[name])
    return MenuItem(label, "insert", f"{name}(", key=key, hint=FUNCTIONS[name])


def cmd(label: str, name: str, key: str = "") -> MenuItem:
    """A leaf that types a command, and a space if it takes arguments (`SortA `)."""
    text = f"{name} " if " " in COMMANDS[name] else name
    return MenuItem(label, "insert", text, key=key, hint=COMMANDS[name])


def conv(label: str, text: str, key: str = "") -> MenuItem:
    """A leaf that types a conversion written after its value (`▶Decimal`)."""
    return MenuItem(label, "insert", text, key=key, hint=CONVERSIONS[text])


def sub(label: str, key: str, *items: MenuItem) -> MenuItem:
    return MenuItem(label, items=items, key=key)


def wiz(label: str, name: str, key: str = "", hint: str = "") -> MenuItem:
    """A leaf that opens dialog `name`; the hint is the command it pastes."""
    return MenuItem(f"{label}…", "wizard", name, key=key, hint=hint)


def todo(label: str, key: str = "") -> MenuItem:
    """A greyed placeholder for a device item CASSim cannot do yet: it keeps its number so the
    keys match the handheld."""
    return MenuItem(label, key=key, hint=NOT_YET, enabled=False)


def todo_sub(label: str, key: str, *labels: str) -> MenuItem:
    """A device submenu none of whose items CASSim has yet: it opens, showing them greyed."""
    return MenuItem(label, key=key, items=tuple(todo(name) for name in labels))


def call(name: str, *args: str) -> str:
    """`name(a,b,c)` with empty trailing arguments dropped (they are optional)."""
    kept = list(args)
    while kept and not kept[-1]:
        kept.pop()
    return f"{name}({','.join(kept)})"


# ---- dialogs ----------------------------------------------------------------------------------

_MU, _SIGMA = Field("mu", "μ", "0"), Field("sigma", "σ", "1")
_LOWER = Field("lower", "Lower Bound", "-∞")  # the device's default is the symbol −∞
_UPPER = Field("upper", "Upper Bound")
_X = Field("x", "X Value")
_AREA = Field("area", "Area")
_DF = Field("df", "Deg of Freedom, df")
_DFN, _DFD = Field("dfn", "Num df"), Field("dfd", "Den df")
_N, _P = Field("n", "Num Trials, n"), Field("p", "Prob Success, p")
_LAMBDA = Field("lam", "λ")
_FREQ = Field("freq", "Frequency List", "1")
_ORDER = Field(
    "order", "Derivative", "1", choices=(("1", "1st Derivative"), ("2", "2nd Derivative"))
)
_SYSTEM_FIELDS = (
    Field("count", "Number of equations", "2", whole=(1, 20)),
    Field("vars", "Variables", "x,y"),
)


# The inverse binomial dialogs end with a Matrix Form box (run 5, E2). Ticked, it adds a last
# argument 1, `invBinom(0.9,10,0.5,1)`, and the answer is a matrix (run 6, R6-D1).
_MATRIX_FORM = Field("matrix", "Matrix Form", "0", toggle=True)


def _dist(title: str, name: str, *fields: Field) -> Wizard:
    """A distribution dialog: pastes `name(fields…)` and runs it on OK, as the handheld does."""
    names = [field.name for field in fields if field is not _MATRIX_FORM]

    def build(values: Mapping[str, str]) -> str:
        ticked = _MATRIX_FORM in fields and values.get(_MATRIX_FORM.name) == "1"
        return call(name, *(values[n] for n in names), *(("1",) if ticked else ()))

    return Wizard(title, fields, run=True, build=build)


def _derivative_at(v: Mapping[str, str]) -> list[Binding]:
    """d/dx(□)|x=Value, as the device pastes it: the variable filled in, the cursor in the box."""
    kind = "derivative" if v["order"] == "1" else "derivative2"
    after = f"|{v['var']}={v['value']}"
    return [
        Binding("template", kind),
        Binding("insert", v["var"]),
        Binding("tab"),  # to the expression
        Binding("tab"),  # out of the template
        Binding("insert", after),
        *(Binding("left") for _ in after),
        Binding("left"),  # back into the expression
    ]


def _system(v: Mapping[str, str], command: str = "solve") -> list[Binding]:
    """`solve(` (or `linSolve(`) with the device's system template and the variables; the
    cursor in the first equation."""
    count, after = int(v["count"]), f",{{{v['vars']}}})"
    return [
        Binding("insert", f"{command}("),
        Binding("template", f"system:{count}"),
        *(Binding("tab") for _ in range(count)),  # out of the template
        Binding("insert", after),
        *(Binding("left") for _ in after),
        Binding("left"),  # into the last equation
        *(Binding("shift_tab") for _ in range(count - 1)),  # back to the first
    ]


def _desolve(v: Mapping[str, str]) -> str:
    """deSolve(equation and conditions, x, y), as the device's dialog pastes it."""
    parts = [v["equation"], *(v[name] for name in ("c1", "c2") if v[name])]
    return f"deSolve({' and '.join(parts)},{v['x']},{v['y']})"


def polynomial(coefficients: str, var: str) -> str:
    """`1,-3,2` in `x` is `x^2-3*x+2` (highest power first)."""
    parts = [c.strip() for c in coefficients.split(",") if c.strip()]
    terms: list[str] = []
    for power, part in zip(range(len(parts) - 1, -1, -1), parts, strict=True):
        if part == "0":
            continue
        c = f"({part})" if any(op in part[1:] for op in "+-") else part
        var_part = "" if power == 0 else var if power == 1 else f"{var}^{power}"
        if not var_part:
            terms.append(c)
        elif c in ("1", "-1"):
            terms.append(c[:-1] + var_part)
        else:
            terms.append(f"{c}*{var_part}")
    return "+".join(terms).replace("+-", "-") or "0"


def _poly_roots(v: Mapping[str, str]) -> str:
    name = "polyRoots" if v["roots"] == "real" else "cZeros"
    return f"{name}({polynomial(v['coeffs'], v['var'])},{v['var']})"


def _regression(title: str, command: str) -> Wizard:
    """Stat Calculations: run the command and show `stat.results` at once, as the handheld does.
    (The device also offers "Save RegEqn to", which needs `CopyVar`.)"""
    fields = (Field("x", "X List"), Field("y", "Y List"), _FREQ)
    return Wizard(title, fields, command + " {x},{y},{freq}: stat.results", run=True)


_TVM_ORDER = ("n", "i", "pv", "pmt", "fv")
_TVM_LABELS = {
    "n": "N",
    "i": "I (%)",
    "pv": "PV",
    "pmt": "Pmt",
    "fv": "FV",
    "ppy": "PpY",
    "cpy": "CpY",
}


def _number(v: Mapping[str, str], name: str) -> float:
    """A box of the Finance Solver as a number: decimals, `ᴇ` or `E`, a fraction `a/b`."""
    text = v.get(name, "").strip().replace("ᴇ", "e").replace("−", "-")
    try:
        top, _, bottom = text.partition("/")
        return float(top) / float(bottom) if bottom else float(top)
    except ValueError, ZeroDivisionError:
        raise ValueError(f"{_TVM_LABELS[name]}: enter a number") from None


def _shown(number: float) -> str:
    text = f"{number:.9g}"  # the iterative interest solve is good to about 9 digits
    return "0" if text == "-0" else text


def finance_calculate(v: Mapping[str, str], target: str) -> dict[str, str]:
    """The Finance Solver's live calculation (the handheld's: put the cursor in a box, press
    Enter): `target` is worked out from the other four values and the timing."""
    if target not in _TVM_ORDER:
        raise ValueError("Choose N, I (%), PV, Pmt or FV to calculate")
    known = {name: _number(v, name) for name in (*_TVM_ORDER, "ppy", "cpy") if name != target}
    pp, cp, at = known["ppy"], known["cpy"], 1 if v.get("pmtat") == "1" else 0
    rate = fin.period_rate(known["i"], pp, cp) if target != "i" else 0.0
    n, pv, pmt, fv = (known.get(name, 0.0) for name in ("n", "pv", "pmt", "fv"))
    solvers = {
        "n": lambda: fin.periods(rate, pv, pmt, fv, at),
        "i": lambda: fin.nominal_percent(fin.interest_rate(n, pv, pmt, fv, at), pp, cp),
        "pv": lambda: fin.present_value(n, rate, pmt, fv, at),
        "pmt": lambda: fin.payment(n, rate, pv, fv, at),
        "fv": lambda: fin.future_value(n, rate, pv, pmt, at),
    }
    try:
        answer = solvers[target]()
    except ValueError, ZeroDivisionError, OverflowError:
        raise ValueError(f"{_TVM_LABELS[target]}: no solution for these values") from None
    if not math.isfinite(answer):
        raise ValueError(f"{_TVM_LABELS[target]}: no solution for these values")
    return {**v, target: _shown(answer)}


def finance_store(v: Mapping[str, str]) -> dict[str, float]:
    """What the Finance Solver leaves in `tvm.n`, `tvm.i`, `tvm.pv`, `tvm.pmt`, `tvm.fv`, `tvm.ppy`,
    `tvm.cpy` and `tvm.pmtat` (the device's names). A box that is not a number is left out."""
    stored: dict[str, float] = {}
    for name in (*_TVM_ORDER, "ppy", "cpy"):
        try:
            stored[f"tvm.{name}"] = _number(v, name)
        except ValueError:
            continue
    stored["tvm.pmtat"] = 1.0 if v.get("pmtat") == "1" else 0.0
    return stored


_REGRESSIONS = (
    ("Linear regression (mx+b)", "LinRegMx", "3"),
    ("Linear regression (a+bx)", "LinRegBx", "4"),
    ("Median-median line", "MedMed", "5"),
    ("Quadratic regression", "QuadReg", "6"),
    ("Cubic regression", "CubicReg", "7"),
    ("Quartic regression", "QuartReg", "8"),
    ("Power regression", "PowerReg", "9"),
    ("Exponential regression", "ExpReg", "A"),
    ("Logarithmic regression", "LnReg", "B"),
    ("Sinusoidal regression", "SinReg", "C"),
    ("Logistic regression (d=0)", "Logistic", "D"),
    ("Logistic regression (d≠0)", "LogisticD", "E"),
)

_BOUNDS_FROM_0 = (Field("lower", "Lower Bound", "0"), Field("upper", "Upper Bound"))
# Dialog titles that differ from the menu label (Cowork run 2, part 2).
_DIST_TITLES = {"invBinom": "Num Successes", "invBinomN": "Num Trials"}
# In the device's order (Probability > 5 and Statistics > 5 are the same list).
_DISTRIBUTIONS = (
    ("Normal Pdf", "normPdf", "1", (_X, _MU, _SIGMA)),
    ("Normal Cdf", "normCdf", "2", (_LOWER, _UPPER, _MU, _SIGMA)),
    ("Inverse normal", "invNorm", "3", (_AREA, _MU, _SIGMA)),
    ("t Pdf", "tPdf", "4", (_X, _DF)),
    ("t Cdf", "tCdf", "5", (_LOWER, _UPPER, _DF)),
    ("Inverse t", "invt", "6", (_AREA, _DF)),
    ("χ² Pdf", "χ²Pdf", "7", (_X, _DF)),
    ("χ² Cdf", "χ²Cdf", "8", (*_BOUNDS_FROM_0, _DF)),
    ("Inverse χ²", "invχ²", "9", (_AREA, _DF)),
    ("Binomial Pdf", "binomPdf", "A", (_N, _P, Field("x", "X Value (optional)"))),
    ("Binomial Cdf", "binomCdf", "B", (_N, _P, *_BOUNDS_FROM_0)),
    ("Inverse binomial", "invBinom", "C", (Field("c", "Cumulative Prob"), _N, _P, _MATRIX_FORM)),
    (
        "Inverse binomial N",
        "invBinomN",
        "D",
        (Field("c", "Cumulative Prob"), _P, Field("x", "Successes, x"), _MATRIX_FORM),
    ),
    ("F Pdf", "FPdf", "E", (_X, _DFN, _DFD)),
    ("F Cdf", "FCdf", "F", (*_BOUNDS_FROM_0, _DFN, _DFD)),
    ("Inverse F", "invF", "G", (_AREA, _DFN, _DFD)),
    ("Geometric Pdf", "geomPdf", "H", (_P, _X)),
    (
        "Geometric Cdf",
        "geomCdf",
        "I",
        (_P, Field("lower", "Lower Bound", "1"), Field("upper", "Upper Bound")),
    ),
    ("Poisson Pdf", "poissPdf", "J", (_LAMBDA, _X)),
    ("Poisson Cdf", "poissCdf", "K", (_LAMBDA, *_BOUNDS_FROM_0)),
)

_STAT_INFERENCE_WIZARDS = {
    name.casefold(): command_wizard(title, name, fields)
    for title, name, _, fields in (*INTERVALS, *TESTS)
}

WIZARDS: dict[str, Wizard] = {
    "derivative_at": Wizard(
        "Derivative at a point",
        (Field("var", "Variable", "x"), Field("value", "Value"), _ORDER),
        steps=_derivative_at,
    ),
    "solve_system": Wizard("Solve a system of equations", _SYSTEM_FIELDS, steps=_system),
    "solve_linear_system": Wizard(
        "Solve a system of linear equations",
        _SYSTEM_FIELDS,
        steps=lambda v: _system(v, "linSolve"),
    ),
    "desolve": Wizard(
        "Differential equation solver",
        (
            Field("equation", "Equation", "y'=2*y"),
            Field("x", "Independent Var", "x"),
            Field("y", "Dependent Var", "y"),
            Field("c1", "Condition (Optional)"),
            Field("c2", "Condition (Optional)"),
        ),
        run=True,
        build=_desolve,
    ),
    "piecewise": Wizard(
        "Create piecewise function",
        (Field("count", "Number of function pieces", "3", whole=(1, 20)),),
        template="piecewise:{count}",
    ),
    "system": Wizard(
        "Create a system of equations",
        (Field("count", "Number of equations", "3", whole=(1, 20)),),
        template="system:{count}",
    ),
    "poly_roots": Wizard(  # the device asks the degree, then the coefficients; it does not run
        "Find roots of a polynomial",
        (
            Field("coeffs", "Coefficients, highest power first", "1,0,-1"),
            Field("var", "Variable", "x"),
            Field("roots", "Roots", "real", choices=(("real", "Real"), ("complex", "Complex"))),
        ),
        build=_poly_roots,
    ),
    "matrix": Wizard(
        "Create a matrix",
        (
            Field("rows", "Number of rows", "2", whole=(1, 99)),
            Field("cols", "Number of columns", "2", whole=(1, 99)),
        ),
        template="matrix:{rows},{cols}",
    ),
    "one_var": Wizard(
        "One-variable statistics",
        (Field("x", "X1 List"), _FREQ),
        "OneVar {x},{freq}: stat.results",
        run=True,
    ),
    "two_var": Wizard(
        "Two-variable statistics",
        (Field("x", "X List"), Field("y", "Y List"), _FREQ),
        "TwoVar {x},{y},{freq}: stat.results",
        run=True,
    ),
    # Live: Enter in a box works it out. Closing pastes nothing, as on the device.
    "finance": Wizard(
        "Finance solver",
        (
            Field("n", "N", "0"),
            Field("i", "I (%)", "0"),
            Field("pv", "PV", "0"),
            Field("pmt", "Pmt", "0"),
            Field("fv", "FV", "0"),
            Field("ppy", "PpY", "1"),
            Field("cpy", "CpY", "1"),
            Field("pmtat", "PmtAt", "0", choices=(("0", "END"), ("1", "BEGIN"))),
        ),
        calculate=finance_calculate,
        store=finance_store,
        copies=(("ppy", "cpy"),),  # changing PpY changes CpY, as on the device
    ),
    **{
        name: _dist(_DIST_TITLES.get(name, title), name, *fields)
        for title, name, _, fields in _DISTRIBUTIONS
    },
    **{command.casefold(): _regression(title, command) for title, command, _ in _REGRESSIONS},
    **_STAT_INFERENCE_WIZARDS,
}


DISTRIBUTIONS = sub(
    "Distributions",
    "5",
    *(wiz(title, name, key, FUNCTIONS[name]) for title, name, key, _ in _DISTRIBUTIONS),
)


def _template_item(label: str, kind: str, name: str, key: str) -> MenuItem:
    """A menu item that pastes a 2D template, as the device's Calculus items do."""
    return MenuItem(label, "template", kind, key=key, hint=FUNCTIONS[name])


# The Calculator's Menu (menu key, F2 on a computer).
MENU = MenuItem(
    "Menu",
    items=(
        sub(
            "Actions",
            "1",
            cmd("Define", "Define", "1"),
            todo("Recall definition", "2"),
            cmd("Delete variable", "DelVar", "3"),
            cmd("Clear a-z…", "ClearAZ", "4"),
            MenuItem("Clear history", "clear", "history", key="5"),
            todo("Insert comment", "6"),
            todo_sub(
                "Library",
                "7",
                "Refresh libraries",
                'Insert "\\" character',
                "Create library shortcut",
                "Define LibPriv",
                "Define LibPub (show in catalog)",
            ),
            todo_sub("Lock", "8", "Lock variable", "Unlock variable", "Get lock info"),
        ),
        sub(
            "Number",
            "2",
            conv("Convert to decimal", "▶Decimal", "1"),
            conv("Approximate to fraction", "▶approxFraction()", "2"),
            fn("Factor", "factor", "3"),
            fn("Least common multiple", "lcm", "4"),
            fn("Greatest common divisor", "gcd", "5"),
            fn("Remainder", "remain", "6"),
            sub(
                "Fraction tools",
                "7",
                fn("Proper fraction", "propFrac", "1"),
                todo("Get numerator", "2"),
                todo("Get denominator", "3"),
                fn("Common denominator", "comDenom", "4"),
            ),
            sub(
                "Number tools",
                "8",
                fn("Round", "round", "1"),
                fn("Integer part", "iPart", "2"),
                fn("Fractional part", "fPart", "3"),
                fn("Sign", "sign", "4"),
                fn("Mod", "mod", "5"),
                fn("Floor", "floor", "6"),
                fn("Ceiling", "ceiling", "7"),
            ),
            sub(
                "Complex number tools",
                "9",
                fn("Complex conjugate", "conj", "1"),
                fn("Real part", "real", "2"),
                fn("Imaginary part", "imag", "3"),
                fn("Polar angle", "angle", "4"),
                fn("Magnitude", "abs", "5"),
                conv("Convert to polar", "▶Polar", "6"),
                conv("Convert to rectangular", "▶Rect", "7"),
            ),
        ),
        sub(
            "Algebra",
            "3",
            fn("Solve", "solve", "1"),
            fn("Factor", "factor", "2"),
            fn("Expand", "expand", "3"),
            fn("Zeros", "zeros", "4"),
            fn("Complete the square", "completeSquare", "5"),
            fn("Numerical solve", "nSolve", "6"),
            sub(
                "Solve system of equations",
                "7",
                wiz(
                    "Solve system of equations",
                    "solve_system",
                    "1",
                    "solve({Eq1, Eq2}, {Var1, Var2})",
                ),
                wiz(
                    "Solve system of linear equations",
                    "solve_linear_system",
                    "2",
                    "linSolve({Eq1, Eq2}, {Var1, Var2})",
                ),
            ),
            sub(
                "Polynomial tools",
                "8",
                wiz("Find roots of polynomial", "poly_roots", "1", FUNCTIONS["polyRoots"]),
                fn("Real roots of polynomial", "polyRoots", "2"),
                fn("Complex roots of polynomial", "cZeros", "3"),
                todo("Remainder of polynomial", "4"),
                todo("Quotient of polynomial", "5"),
                todo("Greatest common divisor", "6"),
                todo("Coefficients of polynomial", "7"),
                todo("Degree of polynomial", "8"),
            ),
            sub(
                "Fraction tools",
                "9",
                fn("Proper fraction", "propFrac", "1"),
                todo("Get numerator", "2"),
                todo("Get denominator", "3"),
                fn("Common denominator", "comDenom", "4"),
            ),
            todo_sub(
                "Convert expression",
                "A",
                "Convert to ln",
                "Convert to logbase",
                "Convert to exp",
                "Convert to sin",
                "Convert to cos",
            ),
            sub("Trigonometry", "B", fn("Expand", "tExpand", "1"), fn("Collect", "tCollect", "2")),
            sub(
                "Complex",
                "C",
                fn("Solve", "cSolve", "1"),
                fn("Factor", "cFactor", "2"),
                fn("Zeros", "cZeros", "3"),
            ),
            sub("Extract", "D", fn("Left", "left", "1"), fn("Right", "right", "2")),
        ),
        sub(
            "Calculus",
            "4",
            _template_item("Derivative", "derivative", "derivative", "1"),
            wiz("Derivative at a point", "derivative_at", "2", "derivative(Expr, Var)|Var=Value"),
            _template_item("Integral", "integral", "∫", "3"),
            _template_item("Limit", "limit", "limit", "4"),
            _template_item("Sum", "sum", "Σ", "5"),
            _template_item("Product", "product", "Π", "6"),
            fn("Function minimum", "fMin", "7"),
            fn("Function maximum", "fMax", "8"),
            fn("Tangent line", "tangentLine", "9"),
            fn("Normal line", "normalLine", "A"),
            todo("Arc length", "B"),
            sub(
                "Series",
                "C",
                fn("Taylor polynomial", "taylor", "1"),
                todo("Generalized series", "2"),
                todo("Dominant term", "3"),
            ),
            wiz("Differential equation solver", "desolve", "D", FUNCTIONS["deSolve"]),
            fn("Implicit differentiation", "impDif", "E"),
            sub(
                "Numerical calculations",
                "F",
                fn("Numerical derivative at a point", "nDerivative", "1"),  # no dialog
                todo("Central difference quotient with step", "2"),
                fn("Numerical integral", "nInt", "3"),
                todo("Numerical function minimum", "4"),
                todo("Numerical function maximum", "5"),
            ),
        ),
        sub(
            "Probability",
            "5",
            MenuItem("Factorial (!)", "insert", "!", key="1", hint="Value!"),
            fn("Permutations", "nPr", "2"),
            fn("Combinations", "nCr", "3"),
            sub(
                "Random",
                "4",
                fn("Number", "rand", "1"),
                fn("Integer", "randInt", "2"),
                fn("Binomial", "randBin", "3"),
                fn("Normal", "randNorm", "4"),
                todo("Sample", "5"),
                cmd("Seed", "RandSeed", "6"),
            ),
            DISTRIBUTIONS,
        ),
        sub(
            "Statistics",
            "6",
            sub(
                "Stat calculations",
                "1",
                wiz("One-variable statistics", "one_var", "1", COMMANDS["OneVar"]),
                wiz("Two-variable statistics", "two_var", "2", COMMANDS["TwoVar"]),
                *(
                    wiz(title, command.casefold(), key, COMMANDS[command])
                    for title, command, key in _REGRESSIONS
                ),
                todo("Multiple linear regression…", "F"),
                todo("Correlation matrix", "G"),
            ),
            MenuItem("Stat results", "insert", "stat.results", key="2", hint="stat.results"),
            sub(
                "List math",
                "3",
                fn("Minimum", "min", "1"),
                fn("Maximum", "max", "2"),
                fn("Mean", "mean", "3"),
                fn("Median", "median", "4"),
                fn("Sum of elements", "sum", "5"),
                fn("Product of elements", "product", "6"),
                fn("Sample standard deviation", "stDevSamp", "7"),
                fn("Sample variance", "varSamp", "8"),
                fn("Population standard deviation", "stDevPop", "9"),
                fn("Population variance", "varPop", "A"),
            ),
            sub(
                "List operations",
                "4",
                cmd("Sort ascending", "SortA", "1"),
                cmd("Sort descending", "SortD", "2"),
                fn("Cumulative sum list", "cumulativeSum", "3"),
                todo("Fill", "4"),
                fn("Sequence", "seq", "5"),
                todo("Difference list", "6"),
                fn("Augment", "augment", "7"),
                fn("Convert list to matrix", "list▶mat", "8"),
                fn("Convert matrix to list", "mat▶list", "9"),
                fn("Left", "left", "A"),
                todo("Mid", "B"),
                fn("Right", "right", "C"),
            ),
            DISTRIBUTIONS,
            sub(
                "Confidence intervals",
                "6",
                *(
                    wiz(title, name.casefold(), key, COMMANDS.get(name, ""))
                    for title, name, key, _ in INTERVALS
                ),
                todo("Multiple reg intervals…", "8"),
            ),
            sub(
                "Stat tests",
                "7",
                *(
                    wiz(title, name.casefold(), key, COMMANDS.get(name, ""))
                    for title, name, key, _ in TESTS
                ),
                todo("Multiple reg tests…", "B"),
                todo("ANOVA…", "C"),
                todo("ANOVA 2-way…", "D"),
            ),
        ),
        sub(
            "Matrix & vector",
            "7",
            sub(
                "Create",
                "1",
                wiz("Matrix", "matrix", "1", "Rows × columns template"),
                todo("Zero matrix", "2"),
                fn("Identity", "identity", "3"),
                todo("Diagonal", "4"),
                todo("Random matrix", "5"),
                todo("Fill", "6"),
                fn("Submatrix", "subMat", "7"),
                fn("Augment", "augment", "8"),
                todo("Column augment", "9"),
                todo("Construct matrix", "A"),
            ),
            conv("Transpose", "ᵀ", "2"),
            fn("Determinant", "det", "3"),
            todo("Row-echelon form", "4"),
            fn("Reduced row-echelon form", "rref", "5"),
            fn("Simultaneous", "simult", "6"),
            sub("Norms", "7", fn("Norm", "norm", "1"), todo("Row", "2"), todo("Column", "3")),
            sub("Dimensions", "8", fn("Matrix", "dim", "1"), todo("Row", "2"), todo("Column", "3")),
            todo_sub(
                "Row operations", "9", "Swap rows", "Row add", "Multiply row", "Multiply row & add"
            ),
            todo_sub(
                "Element operations",
                "A",
                "Dot add",
                "Dot subtract",
                "Dot multiply",
                "Dot divide",
                "Dot power",
            ),
            sub(
                "Advanced",
                "B",
                todo("Trace", "1"),
                todo("LU decomposition", "2"),
                todo("QR decomposition", "3"),
                fn("Eigenvalues", "eigVl", "4"),
                fn("Eigenvectors", "eigVc", "5"),
                todo("Characteristic polynomial", "6"),
            ),
            sub(
                "Vector",
                "C",
                fn("Unit vector", "unitV", "1"),
                fn("Cross product", "crossP", "2"),
                fn("Dot product", "dotP", "3"),
                conv("Convert to polar", "▶Polar", "4"),
                conv("Convert to rectangular", "▶Rect", "5"),
                conv("Convert to cylindrical", "▶Cylind", "6"),
                conv("Convert to spherical", "▶Sphere", "7"),
            ),
        ),
        sub(
            "Finance",
            "8",
            wiz("Finance solver", "finance", "1", "Press Enter in a box to calculate it"),
            sub(
                "TVM functions",
                "2",
                fn("Number of periods", "tvmN", "1"),
                fn("Interest rate per year", "tvmI", "2"),
                fn("Present value", "tvmPV", "3"),
                fn("Payment amount", "tvmPmt", "4"),
                fn("Future value", "tvmFV", "5"),
            ),
            sub(
                "Amortization",
                "3",
                fn("Amortization table", "amortTbl", "1"),
                fn("Balance", "bal", "2"),
                fn("Interest paid", "ΣInt", "3"),
                fn("Principal paid", "ΣPrn", "4"),
            ),
            todo_sub(
                "Cash flows",
                "4",
                "Net present value",
                "Internal rate of return",
                "Modified internal rate of return",
            ),
            sub(
                "Interest conversion",
                "5",
                fn("Nominal interest rate", "nom", "1"),
                fn("Effective interest rate", "eff", "2"),
            ),
            todo_sub("Days between dates", "6", "Month day format", "Day month format"),
        ),
        sub(
            "Functions & programs",
            "9",
            todo_sub("Program Editor", "1", "New…", "Open…", "Import…", "View…"),
            todo("Func…EndFunc", "2"),
            todo("Prgm…EndPrgm", "3"),
            todo("Local", "4"),
            todo_sub(
                "Control",
                "5",
                "If",
                "If…Then…EndIf",
                "If…Then…Else…EndIf",
                "ElseIf…Then",
                "For…EndFor",
                "While…EndWhile",
                "Loop…EndLoop",
                "Try…Else…EndTry",
                "ClrErr",
                "PassErr",
                "errCode",
                "warnCodes",
                "Wait",
            ),
            todo_sub("Transfer", "6", "Return", "Cycle", "Exit", "Lbl", "GoTo Lbl", "Stop"),
            todo_sub(
                "I/O",
                "7",
                "Disp",
                "DispAt",
                "Request",
                "RequestStr",
                "Text",
                "getKey",
                "Get",
                "GetStr",
                "Send",
                "RefreshProbeVars",
            ),
            sub(
                "Mode",
                "8",
                todo_sub(
                    "Display digits",
                    "1",
                    "Float",
                    "Float1",
                    "Float2",
                    "Float3",
                    "Float4",
                    "Float5",
                    "Float6",
                    "Float7",
                    "Float8",
                    "Float9",
                    "Float10",
                    "Float11",
                    "Float12",
                    "Fix0",
                    "Fix1",
                    "Fix2",
                    "Fix3",
                    "Fix4",
                    "Fix5",
                    "Fix6",
                    "Fix7",
                    "Fix8",
                    "Fix9",
                    "Fix10",
                    "Fix11",
                    "Fix12",
                ),
                todo_sub("Angle", "2", "Radian", "Degree", "Gradian"),
                todo_sub("Exponential format", "3", "Normal", "Scientific", "Engineering"),
                todo_sub("Real or complex", "4", "Real", "Rectangular", "Polar"),
                todo_sub("Auto or approx", "5", "Auto", "Approximate", "Exact"),
                todo_sub("Vector format", "6", "Rectangular", "Cylindrical", "Spherical"),
                todo_sub("Base", "7", "Decimal", "Hex", "Binary"),
                todo_sub("Unit system", "8", "SI", "Eng/US"),
                todo("Get mode", "9"),
                todo("Get language info", "A"),
                todo("Get platform info", "B"),
            ),
            todo("Add new line", "9"),
        ),
    ),
)

# Doc (doc key, F4), as on the device.
DOC = MenuItem(
    "Doc",
    items=(
        sub(
            "File",
            "1",
            MenuItem("New document", "new_document", key="1", hint="Ctrl+N"),
            # Open and Save use the documents kept in this browser, by name (FR-DOC-010); files
            # on disk come in and go out through Import and Export (FR-DOC-004, FR-DOC-006)
            MenuItem("Open document", "dialog", "open_document", key="2", hint="Ctrl+O"),
            todo("Close", "3"),
            MenuItem("Save", "dialog", "save", key="4", hint="Ctrl+S"),
            MenuItem("Save as…", "dialog", "save_as", key="5"),
            todo("Send", "6"),
            todo("View copyright information", "7"),
            MenuItem("Import file…", "dialog", "import_file", hint="CASSim"),
            MenuItem("Export file…", "dialog", "export_file", hint="CASSim"),
            MenuItem("Copy share link", "dialog", "share_link", hint="CASSim"),
        ),
        sub(
            "Edit",
            "2",
            MenuItem("Undo", "undo", key="1", hint="Ctrl+Z"),
            MenuItem("Redo", "redo", key="2", hint="Ctrl+Y"),
            MenuItem("Cut", "cut", key="3", hint="Ctrl+X"),
            MenuItem("Copy", "copy", key="4", hint="Ctrl+C"),
            MenuItem("Paste", "paste", key="5", hint="Ctrl+V"),
            MenuItem("Delete", "delete", key="6"),
            todo_sub("Color", "7", "Fill color", "Text color"),
            MenuItem("Move page earlier", "move_page", "-1", hint="CASSim"),
            MenuItem("Move page later", "move_page", "1", hint="CASSim"),
            MenuItem("Move problem earlier", "move_problem", "-1", hint="CASSim"),
            MenuItem("Move problem later", "move_problem", "1", hint="CASSim"),
            MenuItem("Undo page change", "undo_pages", hint="CASSim"),
            MenuItem("Redo page change", "redo_pages", hint="CASSim"),
        ),
        sub(
            "View",
            "3",
            MenuItem("Back", "prev_page", key="1", hint="Ctrl+◀"),
            MenuItem("Forward", "next_page", key="2", hint="Ctrl+▶"),
            MenuItem("Page sorter", "dialog", "page_sorter", key="3", hint="Ctrl+▲"),
        ),
        sub(
            "Insert",
            "4",
            MenuItem("Problem", "add_problem", key="1", hint="then choose an application"),
            MenuItem("Page", "add_page", key="2", hint="Ctrl+I, then choose an application"),
            MenuItem("Calculator", "add_page", "calculator", key="3"),
            MenuItem("Graphs", "add_page", "graphs", key="4"),
            todo("Geometry", "5"),
            MenuItem("Lists & Spreadsheet", "add_page", "spreadsheet", key="6"),
            MenuItem("Data & Statistics", "add_page", "statistics", key="7"),
            MenuItem("Notes", "add_page", "notes", key="8", hint=STUB_PAGE),
            todo("Vernier DataQuest™", "9"),
            todo("Widget", "A"),
            todo_sub("Program Editor", "B", "New…", "Open…", "Import…", "View…"),
            todo_sub("Add Python", "C", "New…", "Open…", "Shell"),
        ),
        sub(
            "Page layout",
            "5",
            todo("Custom split", "1"),
            todo_sub("Select layout", "2", "Layout 1", "Layout 2", "Layout 3"),
            todo("Select app", "3"),
            todo("Swap applications", "4"),
            todo("Delete application", "5"),
            MenuItem("Delete page", "delete_page", key="6"),
            todo("Group", "7"),
            todo("Ungroup", "8"),
        ),
        todo("Refresh libraries", "6"),
        sub(
            "Settings & status",
            "7",
            todo("Change language…", "1"),
            MenuItem("Document settings…", "dialog", "document_settings", key="2"),
            MenuItem("Handheld setup…", "dialog", "system_settings", key="3", hint="CASSim"),
            todo("Status…", "4"),
            todo("Restore factory defaults…", "6"),
        ),
        todo("Login", "8"),
        todo("Press-to-Test", "9"),
    ),
)


# ---- the Calculator's context menus (right-click, ctrl+menu; run 5, H3 j and H5 h) -------------


def history_context(*, warning: bool) -> MenuItem:
    """On a history line: Show Warning Info is greyed unless the line has a warning triangle."""
    return MenuItem(
        "Calculator",
        items=(
            MenuItem("Show warning info…", "context_menu", "warning", key="1", enabled=warning),
            MenuItem("Clear history", "clear", "history", key="2"),
            MenuItem("Copy", "copy", key="3", hint="Ctrl+C"),
            MenuItem("Delete", "delete", key="4", hint="Delete"),
        ),
    )


def entry_context(*, selection: bool, variables: tuple[MenuItem, ...]) -> MenuItem:
    """On the entry line: Cut, Copy and Delete are greyed with nothing selected."""
    return MenuItem(
        "Calculator",
        items=(
            MenuItem("Clear history", "clear", "history", key="1"),
            MenuItem("Cut", "cut", key="2", hint="Ctrl+X", enabled=selection),
            MenuItem("Copy", "copy", key="3", hint="Ctrl+C", enabled=selection),
            MenuItem("Paste", "paste", key="4", hint="Ctrl+V"),
            MenuItem("Delete", "delete", key="5", hint="Delete", enabled=selection),
            MenuItem(
                "Select variable",
                key="6",
                jump=True,
                items=variables or (MenuItem("(none)", "escape"),),
            ),
            MenuItem("Symbols…", "open_menu", "symbols", key="7"),
            MenuItem("Math templates…", "open_menu", "templates", key="8"),
        ),
    )


def _cells(*pairs: tuple[str, str]) -> tuple[MenuItem, ...]:
    """Grid cells that type their text; the label is shown, the hint names it."""
    return tuple(MenuItem(label, "insert", text, hint=text) for label, text in pairs)


_TRIG = ("sin", "cos", "tan", "csc", "sec", "cot")
# The trig key: a 6 × 2 grid, the inverses under their functions. No hyperbolic row.
TRIG = MenuItem(
    "Trig",
    columns=6,
    items=tuple(fn(name, name) for name in (*_TRIG, *(f"{name}⁻¹" for name in _TRIG))),
)

# ctrl+= on the keypad: a 3 × 2 grid (confirmed on the simulator).
RELATIONS = MenuItem(
    "Relations",
    columns=3,
    items=_cells((">", ">"), ("<", "<"), ("≠", "≠"), ("≥", "≥"), ("≤", "≤"), ("|", "|")),
)

# ?!▸: a grid 6 wide.
PUNCTUATION = MenuItem(
    "Punctuation",
    columns=6,
    items=_cells(
        ("?", "?"),
        ("!", "!"),
        ("$", "$"),
        ("°", "°"),
        ("'", "'"),
        ("%", "%"),
        ('"', '"'),
        (":", ":"),
        (";", ";"),
        ("_", "_"),
        ("\\", "\\"),
    ),
)

# π▸: a grid 5 wide (ⅈ and ⅇ are the imaginary unit and Euler's number).
SYMBOLS = MenuItem(
    "Symbols",
    columns=5,
    items=_cells(
        ("π", "π"),
        ("ⅈ", "ⅈ"),
        ("∞", "∞"),
        ("ⅇ", "ⅇ"),
        ("θ", "θ"),
        ("°", "°"),
        ("ʳ", "ʳ"),
        ("ᵍ", "ᵍ"),
        ("'", "'"),
    ),
)


def _cell(label: str, name: str, spec: str, icon: str = "") -> MenuItem:
    """A template cell: `spec` is the template kind, as for the `template` key action, and `icon`
    the picture drawn for it (`app/template_icons.py`), which is `spec` unless given."""
    return MenuItem(label, "template", spec, hint=name, icon=icon or spec)


# The templates key: the device's 25 icons, 11 to a row, in order. Each cell is drawn as a small
# picture of its template (the label is kept as its name in text). Templates CASSim does not have
# yet are greyed.
TEMPLATES = MenuItem(
    "Templates",
    columns=11,
    items=(
        _cell("a/b", "Fraction (ctrl+÷)", "fraction"),
        MenuItem("xʸ", "insert", "^", hint="Exponent (^)", icon="power"),
        _cell("√", "Square root (ctrl+x²)", "root"),
        _cell("ⁿ√", "Nth root (ctrl+^)", "nth_root"),
        MenuItem("eˣ", "insert", "ⅇ^", hint="e exponent (eˣ)", icon="exp"),
        _cell("log", "Log with base (ctrl+10ˣ)", "log"),
        _cell("{2", "Piecewise, 2 pieces", "piecewise:2", "piecewise2"),
        MenuItem("{n", "wizard", "piecewise", hint="Piecewise, N pieces…", icon="piecewise_n"),
        _cell("{=", "System of 2 equations", "system:2", "system2"),
        MenuItem("{n=", "wizard", "system", hint="System of N equations…", icon="system_n"),
        _cell("|x|", "Absolute value", "abs"),
        _cell("°'\"", "Degrees, minutes, seconds", "dms"),
        _cell("2×2", "2 × 2 matrix", "matrix:2,2", "matrix22"),
        _cell("1×2", "1 × 2 matrix", "matrix:1,2", "matrix12"),
        _cell("2×1", "2 × 1 matrix", "matrix:2,1", "matrix21"),
        MenuItem("m×n", "wizard", "matrix", hint="m × n matrix…", icon="matrix_mn"),
        _cell("Σ", "Sum", "sum"),
        _cell("Π", "Product", "product"),
        _cell("d/d", "First derivative (shift+−)", "derivative"),
        _cell("d²", "Second derivative", "derivative2"),
        _cell("dⁿ", "Nth derivative", "derivative_n"),
        _cell("∫ₐᵇ", "Definite integral (shift++)", "integral"),
        _cell("∫", "Indefinite integral", "antiderivative"),
        _cell("lim", "Limit", "limit"),
        MenuItem("x₁", hint="Subscript: " + NOT_YET, enabled=False, icon="subscript"),
        # Not on the device (its lists are typed as {1,2,3}); a comma starts the next element.
        _cell("{ }", "List template (CASSim)", "list:3", "list"),
    ),
)

# The first rows of the Catalog's Symbols tab (the device's grid, 11 wide). Further rows (arrows,
# shapes, currency, set and logic symbols, letters) are left out for now.
_SYMBOL_ROWS = (
    "π ⅇ ⅈ ᴇ ∞ θ → _ ▶ ° ʳ",
    "ᵍ ' ∠ = ≠ < ≤ > ≥ (−) +",
    "− * · × / ÷ ^ ± ᵀ √ ∏",
    "∑ d ∫ ! © @ # $ % & |",
    '" : ; , . ? ( ) { } [',
    "] x̄ ȳ Σ μ σ F χ ² ⁻¹ ₁",
    "₂ ₃ p̂ ŷ c n Δ µ Ω",
)
# Then the Greek capitals and small letters, in Unicode order (no final sigma), 11 to a row.
_GREEK = [chr(c) for c in (*range(0x391, 0x3AA), *range(0x3B1, 0x3CA)) if c not in (0x3A2, 0x3C2)]
_SPECIAL = {"(−)": "-", "−": "-", "^": "^", "√": "√"}


def _symbol_cell(symbol: str) -> MenuItem:
    if symbol == "√":
        return MenuItem("√", "template", "root", hint="Square root")
    return MenuItem(symbol, "insert", _SPECIAL.get(symbol, symbol), hint=symbol)


CATALOG_SYMBOLS = MenuItem(
    "Symbols",
    key="4",
    columns=11,
    items=tuple(_symbol_cell(symbol) for symbol in (*" ".join(_SYMBOL_ROWS).split(), *_GREEK)),
)


def _catalog_entry(name: str) -> MenuItem:
    """A Catalog function, listed as the device lists it: `abs(`."""
    item = fn(name, name)
    return MenuItem(f"{name}(", item.action, item.arg, hint=item.hint)


def _catalog_list() -> MenuItem:
    """Tab 1: every command A to Z in one list with its syntax; a typed letter jumps to it."""
    entries = [(name, _catalog_entry(name)) for name in FUNCTIONS]
    entries += [(name, cmd(name, name)) for name in COMMANDS]
    entries.sort(key=lambda pair: pair[0].casefold())
    return MenuItem("Catalog", key="1", jump=True, items=tuple(item for _, item in entries))


def _tab(item: MenuItem) -> MenuItem:
    """A Catalog tab: no keys of its own, so a digit switches tab as on the device."""
    return MenuItem(item.label, key=item.key, items=item.items, jump=True)


# The catalog key: six tabs, opening on the alphabetical list. Pressing 1 to 6 switches tab.
CATALOG = MenuItem(
    "Catalog",
    start=(0,),
    items=(
        _catalog_list(),
        _tab(todo_sub("Math functions", "2", "Number", "Angle", "List", "Matrix", "Vector")),
        _tab(todo_sub("Units", "3", "Conversion assistant", "Constants", "Length", "Area")),
        CATALOG_SYMBOLS,
        MenuItem("Math expression templates", key="5", columns=11, items=TEMPLATES.items),
        _tab(todo_sub("Library", "6", "Current problem")),
    ),
)

# ---- Lists & Spreadsheet ------------------------------------------------------------------------
# Items and numbering from emulator check 6 (E2, E12 to E14, E18; run 2, E2). Every item a key
# chord or right-click reaches on the emulator is here or in a context menu, so touch reaches it.


def act(label: str, name: str, key: str = "", hint: str = "") -> MenuItem:
    """A sheet page item: `name` is its action (`Spreadsheet.menu_action`)."""
    return MenuItem(label, "sheet", name, key=key, hint=hint)


def _sheet_formula(label: str, text: str, key: str) -> MenuItem:
    """List Math and List Operations: the function goes into the column's formula row with the
    cursor inside its brackets (check 6, E14)."""
    return MenuItem(label, "sheet", f"formula:={text}(", key=key, hint=f"={text}(")


_RESIZE = sub(
    "Resize",
    "2",
    act("Resize column width", "resize", "1", "arrows, then Enter"),
    act("Maximize column width", "maximize", "2"),
    act("Minimize column width", "minimize", "3"),
    todo("Resize row height", "4"),
)

SHEET_MENU = MenuItem(
    "Menu",
    items=(
        sub(
            "Actions",
            "1",
            act("Move column", "move_column", "1", "arrows, then Enter"),
            _RESIZE,
            sub(
                "Select",
                "3",
                act("Select row", "select_row", "1"),
                act("Select column", "select_column", "2"),
                todo("Select formula range", "3"),
            ),
            act("Go to", "goto", "4", "Ctrl+G"),
            act("Recalculate", "recalculate", "5", "Ctrl+R"),
            act("Sort", "sort", "6", "a block first"),
        ),
        sub(
            "Insert",
            "2",
            act("Insert cell", "insert_cell", "1"),
            act("Insert row", "insert_row", "2"),
            act("Insert column", "insert_column", "3"),
        ),
        sub(
            "Data",
            "3",
            act("Generate sequence…", "generate", "1"),
            todo_sub("Data capture", "2", "Automatic", "Manual"),
            act("Fill", "fill", "3", "arrows, then Enter"),
            act("Clear data", "clear", "4"),
            sub(
                "Random",
                "5",
                _sheet_formula("Number", "rand", "1"),
                _sheet_formula("Integer", "randInt", "2"),
                _sheet_formula("Binomial", "randBin", "3"),
                _sheet_formula("Normal", "randNorm", "4"),
                _sheet_formula("Sample", "randSamp", "5"),
            ),
            sub(
                "List math",
                "6",
                _sheet_formula("Minimum", "min", "1"),
                _sheet_formula("Maximum", "max", "2"),
                _sheet_formula("Mean", "mean", "3"),
                _sheet_formula("Median", "median", "4"),
                _sheet_formula("Sum of elements", "sum", "5"),
                _sheet_formula("Product of elements", "product", "6"),
                _sheet_formula("Sample standard deviation", "stDevSamp", "7"),
                _sheet_formula("Sample variance", "varSamp", "8"),
                _sheet_formula("Population standard deviation", "stDevPop", "9"),
                _sheet_formula("Population variance", "varPop", "A"),
            ),
            sub(
                "List operations",
                "7",
                _sheet_formula("Cumulative sum list", "cumulativeSum", "1"),
                _sheet_formula("Difference list", "deltaList", "2"),
                _sheet_formula("Augment", "augment", "3"),
                todo("Convert matrix to list", "4"),
                _sheet_formula("Left", "left", "5"),
                _sheet_formula("Mid", "mid", "6"),
                _sheet_formula("Right", "right", "7"),
            ),
            act("Summary plot", "summary_plot", "8"),
            act("Quick graph", "quick_graph", "9"),
            sub(
                "Import/export",
                "A",
                MenuItem("Import CSV…", "dialog", "sheet_import_csv"),
                MenuItem("Export CSV…", "dialog", "sheet_export_csv"),
                MenuItem("Import XLSX…", "dialog", "sheet_import_xlsx"),
                MenuItem("Export XLSX…", "dialog", "sheet_export_xlsx"),
            ),
        ),
        sub(
            "Statistics",
            "4",
            sub(
                "Stat calculations",
                "1",
                act("One-variable statistics…", "onevar", "1"),
                *(act(f"{label}…", f"stat:{name}", key) for label, name, key in STAT_CALCULATIONS),
                todo("Multiple linear regression…", "F"),
            ),
            # From a sheet these write their formula into the selected cell (run 4, S10)
            replace(
                DISTRIBUTIONS,
                key="2",
                items=tuple(
                    # Normal Cdf on a sheet has Draw: Shade area (split2 H14)
                    replace(item, action="sheet", arg="distribution:normCdf")
                    if item.arg == "normCdf"
                    else item
                    for item in DISTRIBUTIONS.items
                ),
            ),
            sub(
                "Confidence intervals",
                "3",
                *(
                    act(f"{item.title}…", f"inference:{item.command}", item.key)
                    for item in sheet_inference.INTERVALS
                ),
                todo("Multiple reg intervals…", "8"),
            ),
            sub(
                "Stat tests",
                "4",
                *(
                    act(f"{item.title}…", f"inference:{item.command}", item.key)
                    for item in sheet_inference.TESTS
                ),
                todo("Multiple reg tests…", "B"),
                todo("ANOVA…", "C"),
                todo("ANOVA 2-way…", "D"),
            ),
        ),
        todo("Table", "5"),
    ),
)

_CUT_COPY_PASTE = (
    act("Cut", "cut", "1", "Ctrl+X"),
    act("Copy", "copy", "2", "Ctrl+C"),
    act("Paste", "paste", "3", "Ctrl+V"),
)

# Context menus: a long press (touch), a right-click, or ctrl+menu.
SHEET_CELL = MenuItem(
    "Cell",
    items=(
        *_CUT_COPY_PASTE,
        act("Insert cell", "insert_cell", "4"),
        act("Delete cell", "delete_cell", "5"),
        act("Fill", "fill", "6"),
        sub(
            "Variables",
            "7",
            act("Store var", "store_var", "1"),
            act("Unlink", "unlink", "2"),
        ),
        replace(_RESIZE, key="8"),
        act("Summary plot", "summary_plot", "9"),
        act("Quick graph", "quick_graph", "A"),
        todo("Color", "B"),
    ),
)
SHEET_BLOCK = MenuItem(
    "Cells",
    items=(
        *_CUT_COPY_PASTE,
        act("Fill", "fill", "4"),
        act("Delete cells", "delete_cells", "5"),
        act("Sort", "sort", "6"),
        todo("Color", "7"),
        act("Summary plot", "summary_plot", "8"),
        act("Quick graph", "quick_graph", "9"),
    ),
)
SHEET_ROW = MenuItem(
    "Row",
    items=(
        *_CUT_COPY_PASTE,
        todo("Resize row", "4"),
        act("Insert row", "insert_row", "5"),
        act("Delete row", "delete_row", "6"),
        todo("Color", "7"),
    ),
)
# The name cell's context menu (run 4, S12): Cut greyed, no Copy, no Insert or Delete Column.
SHEET_NAME = MenuItem(
    "Column",
    items=(
        todo("Cut", "1"),
        act("Paste", "paste", "2"),
        sub(
            "Variables",
            "3",
            act("Store var", "store_var", "1"),
            act("Unlink", "unlink", "2"),
        ),
        replace(_RESIZE, key="4"),
        act("Summary plot", "summary_plot", "5"),
        act("Quick graph", "quick_graph", "6"),
        todo("Color", "7"),
    ),
)
SHEET_COLUMN = MenuItem(
    "Column",
    items=(
        *_CUT_COPY_PASTE,
        act("Insert column", "insert_column", "4"),
        act("Delete column", "delete_column", "5"),
        act("Move column", "move_column", "6"),
        replace(_RESIZE, key="7"),
        todo("Data", "8"),
        todo("Color", "9"),
    ),
)


def _app_picker(action: Action, title: str) -> MenuItem:
    """The list of applications a new page or Problem offers (emulator checks: graphs2 D, graphs3,
    sharing G, split H): the device's ten items and numbers; Geometry, Vernier DataQuest and
    Widget are greyed; Notes, Program Editor and Python are not built yet."""

    def add(label: str, kind: str, key: str, *, stub: bool = False) -> MenuItem:
        return MenuItem(f"Add {label}", action, kind, key=key, hint=STUB_PAGE if stub else "")

    return MenuItem(
        title,
        items=(
            add("Calculator", "calculator", "1"),
            add("Graphs", "graphs", "2"),
            todo("Add Geometry", "3"),
            add("Lists & Spreadsheet", "spreadsheet", "4"),
            add("Data & Statistics", "statistics", "5"),
            add("Notes", "notes", "6", stub=True),
            todo("Add Vernier DataQuest™", "7"),
            todo("Add widget", "8"),
            add("Program Editor", "program", "9", stub=True),
            add("Python", "python", "A", stub=True),
        ),
    )


ADD_PAGE = _app_picker("add_page", "Add a page")
ADD_PROBLEM = _app_picker("add_problem", "Add a Problem")

MENUS = {
    "doc": DOC,
    "menu": MENU,
    "menu_sheet": SHEET_MENU,
    "add_page": ADD_PAGE,
    "add_problem": ADD_PROBLEM,
    "sheet_cell": SHEET_CELL,
    "sheet_block": SHEET_BLOCK,
    "sheet_row": SHEET_ROW,
    "sheet_column": SHEET_COLUMN,
    "sheet_name": SHEET_NAME,
    "trig": TRIG,
    "templates": TEMPLATES,
    "catalog": CATALOG,
    "relations": RELATIONS,
    "punctuation": PUNCTUATION,
    "symbols": SYMBOLS,
}
