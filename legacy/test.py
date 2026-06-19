import markdown

# Sample Markdown input with tables and LaTeX math
markdown_content = """
# Example Markdown

Here is a table:

| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Value 1  | Value 2  | Value 3  |

Here is some math:

Inline math: $E=mc^2$

Block math:
$$
\\int_{-\\infty}^{\\infty} e^{-x^2} dx = \\sqrt{\\pi}
$$
"""

# Convert Markdown to HTML
html_content = markdown.markdown(
    markdown_content, extensions=["tables", "mdx_math"]  # Add "extra" for other extended Markdown features
)

# Add MathJax script for rendering LaTeX math
mathjax_script = """
<script type="text/javascript" async
  src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js">
</script>
"""

# Combine HTML content with MathJax script
html_output = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Markdown to HTML</title>
</head>
<body>
{html_content}
{mathjax_script}
</body>
</html>
"""

# Save the output to an HTML file
with open("output.html", "w", encoding="utf-8") as f:
    f.write(html_output)

print("Markdown converted to HTML and saved as 'output.html'")
