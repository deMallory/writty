---
type: Guide
title: "Tantivy and BM25"
description: How keyword search scores a document, how Writty builds an in-memory Tantivy index, and a small index you can run yourself.
---

# Tantivy and BM25

Tantivy is a full-text search library written in Rust. BM25 is the formula it uses to score a document against a query. A rare word counts more than a word that appears in almost every document. Reach for it when you have a pile of texts in one process and the query is words a person actually typed.

This page teaches the idea. The weights inside Writty's pipeline are in `docs/reference/retrieval.md`.

## The idea, on three sentences

Take three notes:

| Id | Text |
|---|---|
| param | Use a parameterized query for SQL |
| user | The query returns the user |
| inject | Parameterize every SQL query. A query built by concatenation is injectable |

A search engine does not scan the sentences at query time. It builds an inverted index: for each token, the list of documents that contain it.

| Token | Documents |
|---|---|
| parameterized | param |
| parameterize | inject |
| sql | param, inject |
| query | param, user, inject |

Two consequences fall out of that table.

- "query" is in every note, so it does not separate them. "parameterized" is in one note, so it does.
- "parameterized" and "Parameterize" are different tokens. Tantivy's default tokenizer folds case (`SQL` and `sql` meet) and does not stem word forms. A paraphrase is a miss. That miss is what the vector stage is for. See [ONNX embeddings](onnx.md).

BM25 turns those lists into a score. The usual shape has two parts. Term frequency asks how often the word appears in this document. Inverse document frequency asks in how few documents it appears at all. A word in one document out of a thousand outranks a word in nine hundred of them, even when the common word is repeated.

Running that toy through the same `tantivy` package Writty imports, the query `parameterized SQL` returns `param` first and `inject` second. `user` is absent: it has neither token. The raw BM25 number is useful only for ordering inside one index. Do not compare it with a score from another index, or with a cosine.

## A small index you can run

This is the whole loop: declare a schema, add documents, commit, search. No path means the index stays in memory, which is what `KeywordIndex` does when it is constructed without a directory (`writ/retrieval/keyword.py`).

```python
import tantivy

builder = tantivy.SchemaBuilder()
builder.add_text_field("doc_id", stored=True)
builder.add_text_field("body", stored=True)
index = tantivy.Index(builder.build())

writer = index.writer()
writer.add_document(tantivy.Document(
    doc_id="param",
    body="Use a parameterized query for SQL",
))
writer.add_document(tantivy.Document(
    doc_id="user",
    body="The query returns the user",
))
writer.commit()
index.reload()

searcher = index.searcher()
query = index.parse_query("parameterized SQL", ["body"])
for score, address in searcher.search(query, 5).hits:
    print(searcher.doc(address)["doc_id"][0], score)
```

`stored=True` keeps the original text so a hit can return the id. The query names the fields it may match. `reload` is required after `commit`, or the searcher still sees the empty index.

## How Writty uses it

`KeywordIndex.build` in `writ/retrieval/keyword.py` runs at service startup, over the rules that are allowed into the ranked pool. Mandatory rules are skipped here on purpose, and delivered by another path. See [Retrieval](retrieval.md).

Three details are worth stealing only if you know why they exist:

| Choice | What the code does | Why |
|---|---|---|
| Trigger counts double | The trigger string is inserted twice (`TRIGGER_BOOST` is 2) | The trigger is the condition that should fire the rule. Repeating it raises its term frequency |
| Body counts half | Only every other body token is indexed | A long explanation would otherwise drown the trigger and the statement |
| A bad query returns nothing | Characters that break the parser are stripped, and a `ValueError` from `parse_query` returns an empty list | Keyword search can fail closed. The vector stage still runs |

The searched fields are `trigger`, `statement`, `tags`, and `body`. `rule_id` is stored so the hit can name the rule. The pipeline asks for 50 hits (`search` in `writ/retrieval/keyword.py`).

## Where this pays off in another project

Use Tantivy when the texts fit in one process and you want search without operating a cluster. A help center, a rulebook, a local code index, and a mailbox search on one machine all fit.

A `LIKE` prefix on one column answers a narrower question and needs no index library. A separate search cluster earns its keep when many services share a corpus larger than one machine, or when the index must survive the process that built it. Writty rebuilds the Tantivy index on every service start. That is acceptable because the corpus is small and the source of truth is Neo4j, not the index.

If you persist a Tantivy index, rebuild it when the source texts change, and treat a failed `parse_query` as zero hits rather than a crashed request. Users type quotes, slashes, and the words `AND` and `OR`. Writty strips the special characters and lowercases those reserved words before parsing (`_TANTIVY_SPECIAL` and `_TANTIVY_RESERVED` in `writ/retrieval/keyword.py`).

## Where to go next

- [The core stack](core-stack.md): where keyword search sits in a prompt.
- [ONNX embeddings](onnx.md): the stage that catches the paraphrase BM25 misses.
- [hnswlib](hnswlib.md): the index over those embeddings.
