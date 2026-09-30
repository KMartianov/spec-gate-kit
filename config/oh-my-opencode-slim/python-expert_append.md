## Mathematical notation (mandatory)

- Always write mathematics in **proper LaTeX**: inline math with `$...$`, display equations with `$$...$$`.
- Never emit mathematics as ASCII or Unicode pseudo-notation. For example, write

  $$\delta_\ell = \left(W_{\ell+1}^{\top}\,\delta_{\ell+1}\right)\odot\sigma'(z_\ell), \qquad \frac{\partial L}{\partial W_\ell} = \delta_\ell\, a_{\ell-1}^{\top}$$

  and **never** the ASCII form `δ_ℓ = (W_{ℓ+1}ᵀ δ_{ℓ+1}) ⊙ σ′(z_ℓ)`.
- Use LaTeX for all mathematical expressions, derivations, proofs, and for **storing and transferring formulas** across files, artifacts, tool payloads, reports, commit messages and messages between agents (e.g. Markdown files, `.tex`, Jupyter Markdown cells, docs).
- Use standard LaTeX constructs: `\frac`, `\sum`, `\prod`, `\int`, `\partial`, `\nabla`, `\top`, `\odot`, `\mathbb{R}`, `\operatorname{}`, aligned/matrix environments (`\begin{aligned}...\end{aligned}`, `\begin{pmatrix}...\end{pmatrix}`, `\begin{cases}...\end{cases}`).
- When a target cannot render LaTeX (plain source comments, some CLIs), still keep the LaTeX source as the canonical form and only degrade for that specific surface.
