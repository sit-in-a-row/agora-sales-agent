# How to retrieve without a Vector DB

MVP는 `document_index.csv`를 표준 `csv` 모듈로 읽고 tag/doc_id를 기준으로 candidate 문서를 좁힌다.

```python
import csv
from pathlib import Path

ROOT = Path("knowledge/agora_sales_retrieval_dataset_v1")
with (ROOT / "00_meta/document_index.csv").open(encoding="utf-8-sig") as f:
    index = list(csv.DictReader(f))

keywords = ["retail", "sales", "CRM"]
hits = [
    row for row in index
    if any(k.lower() in (row.get("tags") or "").lower() for k in keywords)
]

documents = [
    (ROOT / row["path"]).read_text(encoding="utf-8")
    for row in hits[:6]
]
```

이후 Account Research의 industry / department / interest / business signals와 함께 Strategist에게 전달한다.

v1의 원칙은 embedding보다 **작고 잘 분리된 문서 + 명시적 tags + LLM semantic selection**이다.
