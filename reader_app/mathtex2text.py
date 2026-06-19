from __future__ import annotations

from pylatexenc.latexwalker import (
    LatexWalker,
    LatexCharsNode,
    LatexMacroNode,
    LatexGroupNode,
    LatexMathNode,
    LatexNode,
)


def process_latex_node(node: LatexNode) -> str:
    """Recursively process a LaTeX node and convert it into spoken text."""
    if isinstance(node, LatexCharsNode):
        # Plain text or symbols
        chars = node.chars
        # Convert '+' to 'plus' and '-' to 'minus'
        chars = (
            chars.replace("+", " plus ")
            .replace("-", " minus ")
            .replace("=", " equals ")
            .replace(">", " greater than ")
            .replace("<", " less than ")
            .replace("≥", " greater than or equal to ")
            .replace("≤", " less than or equal to ")
            .replace("≠", " not equal to ")
            .replace("∞", " infinity ")
            .replace("∑", " sum ")
            .replace("∫", " integral ")
            .replace("√", " square root ")
            .replace("π", " pi ")
            .replace("α", " alpha ")
            .replace("β", " beta ")
            .replace("γ", " gamma ")
            .replace("δ", " delta ")
            .replace("θ", " theta ")
            .replace("λ", " lambda ")
            .replace("μ", " mu ")
            .replace("σ", " sigma ")
            .replace("ω", " omega ")
            .replace("∆", " delta ")
            .replace("∇", " nabla ")
            .replace("∈", " element of ")
            .replace("∉", " not an element of ")
            .replace("∩", " intersection ")
            .replace("∪", " union ")
            .replace("⊆", " subset of ")
            .replace("⊇", " superset of ")
            .replace("⊂", " proper subset of ")
            .replace("⊃", " proper superset of ")
            .replace("∅", " empty set ")
            .replace("∀", " for all ")
            .replace("∃", " there exists ")
            .replace("∄", " there does not exist ")
            .replace("∞", " infinity ")
            .replace("∝", " proportional to ")
            .replace(" |", " given ")
        )
        return chars
    elif isinstance(node, LatexMacroNode):
        if node.macroname in ["left", "right", "displaystyle", "textstyle", "scriptstyle", "scriptscriptstyle"]:
            return ""  # Skip the \left or \right macros

        # Ignore math fonts like \mathcal, \mathbb, \mathbf, etc.
        if node.macroname in ["mathcal", "mathbb", "mathbf", "mathsf", "mathit", "text", "mathrm", "mathscr"]:
            # Just process the content inside these macros
            return " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()

        # Handle macros like \frac, \sqrt, \pi, etc.
        if node.macroname == "frac":
            numerator = process_latex_node(node.nodeargd.argnlist[0])  # First argument of \frac
            denominator = process_latex_node(node.nodeargd.argnlist[1])  # Second argument of \frac
            return f"fraction of {numerator} over {denominator}"
        elif node.macroname == "sqrt":
            content = " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # Argument of \sqrt
            return f"square root of {content}"
        elif node.macroname == "pi":
            return "pi"
        elif node.macroname == "sum":
            return "sum of"
        elif node.macroname == "int":
            return "integral of"
        elif node.macroname == "alpha":
            return "alpha"
        elif node.macroname == "beta":
            return "beta"
        elif node.macroname == "gamma":
            return "gamma"
        elif node.macroname == "dot":
            content = " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # Argument of \sqrt
            return f"{content} dot"
        elif node.macroname == "tilde":
            content = " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # Argument of \sqrt
            return f"{content} tilde"
        elif node.macroname == "hat":
            content = " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # Argument of \sqrt
            return f"{content} hat"
        elif node.macroname == "bar":
            content = " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # Argument of \sqrt
            return f"{content} bar"
        elif node.macroname == "vec":
            content = " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # Argument of \sqrt
            return f"{content} vector"
        elif node.macroname == "prime":
            content = " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # Argument of \sqrt
            return f"{content} prime"
        # Handle common math functions
        elif node.macroname == "cos":
            content = " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # Argument of \sqrt
            return f"cosine of {content}"
        elif node.macroname == "sin":
            content = " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # Argument of \sqrt
            return f"sine of {content}"
        elif node.macroname == "tan":
            content = " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # Argument of \sqrt
            return f"tangent of {content}"
        elif node.macroname == "log":
            content = " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # Argument of \sqrt
            return f"logarithm of {content}"
        elif node.macroname == "ln":
            content = " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # Argument of \sqrt
            return f"natural logarithm of {content}"
        elif node.macroname == "exp":
            content = " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # Argument of \sqrt
            return f"exponential of {content}"
        elif node.macroname == "lvert" or node.macroname == "rvert":
            return (
                "absolute value of " + " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()
            )  # | ... |
        elif node.macroname == "lVert" or node.macroname == "rVert":
            return "norm of " + " ".join(process_latex_node(n) for n in node.nodeargd.argnlist).strip()  # || ... ||
        elif node.macroname == "ldots" or node.macroname == "cdots" or node.macroname == "vdots":
            return "dot dot dot"
        elif node.macroname == "infty":
            return "infinity"
        elif node.macroname == "forall":
            return "for all"
        elif node.macroname == "exists":
            return "there exists"
        elif node.macroname.startswith("var"):
            return node.macroname[3:]  # Remove "var" prefix
        else:
            return node.macroname  # Fallback for unhandled macros
    elif isinstance(node, LatexGroupNode):
        # Process grouped content (e.g., braces {})
        if node.nodelist:
            node_str = " ".join(process_latex_node(n) for n in node.nodelist)
            return node_str
        return ""
        # return process_latex_node(node.nodelist[0]) if node.nodelist else ""
    elif isinstance(node, LatexMathNode):
        # Process math mode expressions (e.g., $...$ or \[...\])
        return " ".join(process_latex_node(n) for n in node.nodelist)
    return ""


def parse_superscripts_and_subscripts(latex_string: str) -> str:
    """Convert explicit LaTeX super/subscript markers into spoken fragments."""
    spoken = ""
    i = 0
    while i < len(latex_string):
        if latex_string[i] == "^":
            spoken += " to the power of "
            i += 1
            if i < len(latex_string) and latex_string[i] == "{":
                # Read grouped superscript
                j = i + 1
                group = ""
                while j < len(latex_string) and latex_string[j] != "}":
                    group += latex_string[j]
                    j += 1
                spoken += group
                i = j  # Skip to the closing brace
            else:
                # Read single character superscript
                spoken += latex_string[i]
        elif latex_string[i] == "_":
            # spoken += " sub "
            spoken += "  "
            i += 1
            if i < len(latex_string) and latex_string[i] == "{":
                # Read grouped subscript
                j = i + 1
                group = ""
                while j < len(latex_string) and latex_string[j] != "}":
                    group += latex_string[j]
                    j += 1
                spoken += group
                i = j  # Skip to the closing brace
            else:
                # Read single character subscript
                spoken += latex_string[i]
        else:
            spoken += latex_string[i]
        i += 1
    return spoken


def latex_to_speech_with_latexwalker(latex_code: str) -> str:
    """Convert a LaTeX math string into spoken text using latexwalker parsing."""
    walker = LatexWalker(latex_code)
    nodes, _, _ = walker.get_latex_nodes()

    # Process each node and convert it to spoken form
    spoken_parts = [process_latex_node(node) for node in nodes]
    spoken_string = " ".join(spoken_parts)

    # Handle superscripts and subscripts
    spoken_string = parse_superscripts_and_subscripts(spoken_string)
    return spoken_string
