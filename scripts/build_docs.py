"""Собирает docs/DOCUMENTATION.md: шаблон + актуальные результаты валидации (запускать после validate.py)."""
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "docs"
t = (D / "_doc_template.md").read_text(encoding="utf-8")
v = (D / "VALIDATION_RESULTS.md").read_text(encoding="utf-8").split("\n", 1)[1].lstrip()
v = v.replace("\n## A.", "\n#### A.").replace("\n## ", "\n#### ")
if v.startswith("## "):
    v = "#" * 4 + v[2:]
(D / "DOCUMENTATION.md").write_text(t.replace("{{VALIDATION}}", v), encoding="utf-8")
print("docs/DOCUMENTATION.md обновлён")
