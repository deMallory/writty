---
type: Guide
title: "ONNX embeddings"
description: How a sentence becomes a vector, how Writty runs all-MiniLM-L6-v2 through ONNX Runtime, and a cosine you can reproduce.
---

# ONNX embeddings

ONNX is a file format for a frozen model. ONNX Runtime is the program that executes that file. Writty uses the pair to turn a sentence into 384 numbers, so two sentences can be compared by the angle between them. Reach for it when a production process must run a model, and the training tools should stay out of that process.

This page teaches the idea. The abstention threshold and the ranking weight on this score are in `docs/reference/retrieval.md`.

## The idea

A keyword index matches tokens. It misses "bind variables instead of concatenating SQL" when the document says "parameterized query". An embedding model reads the whole sentence and emits a vector. Sentences about the same thing point roughly the same way.

The score Writty uses is cosine similarity. After both vectors are scaled to length 1, cosine is their dot product: 1 when they are the same direction, 0 when they are unrelated, negative when they oppose.

These three pairs were encoded with `OnnxEmbeddingModel` in `writ/retrieval/embeddings.py`, model `all-MiniLM-L6-v2`, on the exported file this repo's bootstrap produces:

| Cosine | Left | Right |
|---:|---|---|
| 1.000 | Use a parameterized query for SQL | the same sentence |
| 0.528 | Use a parameterized query for SQL | Bind variables instead of concatenating SQL |
| 0.018 | Use a parameterized query for SQL | The cafeteria serves soup on Tuesday |

The paraphrase shares almost no tokens with the original and still scores 0.528. The unrelated sentence scores about 0. The pipeline's abstention cut, `RULE_INJECTION_ABSTENTION_THRESHOLD` in `writ/retrieval/pipeline.py`, is 0.30 on this same raw cosine. A paraphrase of a rule can clear it. A sentence about lunch does not. Those two sentences are an illustration of the model, not the set the threshold was tuned on.

## What actually runs

`all-MiniLM-L6-v2` is a small public sentence model. Writty does not ship the training stack in the service. `scripts/export_onnx.py` runs once, with `optimum`, and writes `model.onnx` plus `tokenizer.json`. The service loads those two files.

`OnnxEmbeddingModel.encode` does three steps:

1. Tokenize with the Rust `tokenizers` library. Truncate and pad to 128 tokens (`MAX_LENGTH`).
2. Run the ONNX session on the CPU provider. The outputs are one vector per token.
3. Mean-pool, then divide by the vector's length. The attention mask zeroes the padding, so pad tokens do not move the average.

```python
import numpy as np
from writ.retrieval.embeddings import OnnxEmbeddingModel

model = OnnxEmbeddingModel()  # reads model.onnx and tokenizer.json from the user cache
left = model.encode("Use a parameterized query for SQL")
right = model.encode("Bind variables instead of concatenating SQL")
cosine = float(np.dot(left, right))  # both vectors already have length 1
```

`left.shape` is `(384,)`. That width is fixed for this model. `writ/retrieval/pipeline.py` passes `dimensions=384` when it builds the vector index. A different model means a different width, and the index must be rebuilt.

Repeated prompts hit an LRU of 1,024 encodings (`CachedEncoder` in `writ/retrieval/embeddings.py`). The rules themselves are encoded in bulk when the index is built, not on the prompt.

## A model of your own, same shape

The export and the runtime are different programs. Keep them that way.

Export, once, on a machine that has the training libraries:

```python
from optimum.onnxruntime import ORTModelForFeatureExtraction
from transformers import AutoTokenizer

name = "sentence-transformers/all-MiniLM-L6-v2"
out = "models/onnx"
ORTModelForFeatureExtraction.from_pretrained(name, export=True).save_pretrained(out)
AutoTokenizer.from_pretrained(name).save_pretrained(out)
```

Runtime, on every machine that serves traffic:

```python
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

tokenizer = Tokenizer.from_file("models/onnx/tokenizer.json")
tokenizer.enable_truncation(max_length=128)
tokenizer.enable_padding(length=128)
session = ort.InferenceSession(
    "models/onnx/model.onnx",
    providers=["CPUExecutionProvider"],
)

def embed(text: str) -> np.ndarray:
    enc = tokenizer.encode(text)
    feeds = {
        "input_ids": np.array([enc.ids], dtype=np.int64),
        "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
        "token_type_ids": np.array([enc.type_ids], dtype=np.int64),
    }
    token_vectors = session.run(None, feeds)[0]
    mask = feeds["attention_mask"][..., None].astype(np.float32)
    pooled = (token_vectors * mask).sum(axis=1) / mask.sum(axis=1)
    return pooled / np.linalg.norm(pooled, axis=1, keepdims=True)
```

That `embed` is the same three steps as `_tokenize`, the session call, and `_pool_and_normalize` in `writ/retrieval/embeddings.py`. The input names (`input_ids`, `attention_mask`, `token_type_ids`) match this MiniLM export. Another architecture can name its inputs differently: read `session.get_inputs()` before you assume them.

Check the runtime against a known pair before you trust an index built from it. The 0.528 pair above is a fine fixture. If a new export moves that cosine, the index and the threshold were built for a different function.

## Where this pays off in another project

Use ONNX when the model is a dependency of a request path: search, routing, deduplication, "is this text about that text". The process then imports `onnxruntime`, `tokenizers`, and `numpy`. The machine that serves traffic does not need PyTorch installed.

Keep the training framework for the export, for fine-tuning, and for the notebook where you decide the model is good enough. Writty's fallback, enabled only with `WRIT_ALLOW_EMBEDDING_FALLBACK=1`, is the sentence-transformers path. The default is the ONNX file. A missing file raises, so a deploy cannot silently switch models.

Two limits belong in the design. The model only sees 128 tokens, so a long document needs a policy (first paragraph, a summary, a sliding window) before you embed it. And cosine compares the texts you embedded. It does not know that one of them is authoritative. Writty handles authority outside the model, in the ranker (`writ/retrieval/ranking.py`).

## Where to go next

- [The core stack](core-stack.md): where the embedding sits in a prompt.
- [Tantivy and BM25](tantivy.md): the keyword stage, which catches the exact token this model can blur.
- [hnswlib](hnswlib.md): how those 384-vectors are searched without scanning all of them.
