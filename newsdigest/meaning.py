"""Merge groups of headlines that describe the same event in different words.

Word overlap misses "RBA lifts cash rate" versus "Reserve Bank raises interest rates".
Gemini's free embedding model turns each headline into a list of numbers (a meaning
fingerprint); two fingerprints pointing the same way mean the same thing. Any failure
falls back to the word based groups unchanged.
"""

import math
import os
import re

import requests

from .diagnostics import report

GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"
BATCH = 100
_model = None


def _embedding_model(key):
    global _model
    if _model:
        return _model
    resp = requests.get(f"{GEMINI_API}/models", params={"pageSize": 1000}, headers={"x-goog-api-key": key}, timeout=30)
    resp.raise_for_status()
    names = [m["name"] for m in resp.json().get("models", [])
             if "embedContent" in m.get("supportedGenerationMethods", [])]
    # Prefer the newest gemini-embedding model, then any text-embedding model.
    def rank(name):
        version = re.findall(r"\d+", name)
        return ("gemini-embedding" in name, [int(v) for v in version])
    if not names:
        raise RuntimeError("no embedding model is available")
    _model = max(names, key=rank)
    return _model


def embed(texts):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("no Gemini key")
    model = _embedding_model(key)
    vectors = []
    for i in range(0, len(texts), BATCH):
        body = {"requests": [{"model": model, "content": {"parts": [{"text": t}]}} for t in texts[i:i + BATCH]]}
        resp = requests.post(f"{GEMINI_API}/{model}:batchEmbedContents", headers={"x-goog-api-key": key}, json=body, timeout=60)
        resp.raise_for_status()
        vectors += [e["values"] for e in resp.json()["embeddings"]]
    return vectors


def _unit(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _centroid(vectors):
    return _unit([sum(col) / len(vectors) for col in zip(*vectors)])


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def merge_groups(groups, threshold, embed_fn=embed):
    """groups: lists of Items. Returns fewer or equal groups."""
    if len(groups) < 2:
        return groups
    titles = [i.title for g in groups for i in g]
    try:
        vectors = embed_fn(titles)
    except Exception as exc:  # network, quota or format problems
        report.ai_notes.append(f"Meaning based merging skipped ({str(exc)[:120]}); used word matching only.")
        return groups
    per_group, pos = [], 0
    for g in groups:
        per_group.append(_centroid([_unit(v) for v in vectors[pos:pos + len(g)]]))
        pos += len(g)
    order = sorted(range(len(groups)), key=lambda k: -len(groups[k]))
    merged, centres, members = [], [], []
    for k in order:
        best, best_sim = None, threshold
        for m, c in enumerate(centres):
            sim = _cos(per_group[k], c)
            if sim >= best_sim:
                best, best_sim = m, sim
        if best is None:
            merged.append(list(groups[k]))
            centres.append(per_group[k])
            members.append([per_group[k]])
        else:
            merged[best].extend(groups[k])
            members[best].append(per_group[k])
            centres[best] = _centroid(members[best])
    if len(merged) < len(groups):
        report.ai_notes.append(f"Meaning based merging joined {len(groups) - len(merged)} duplicate groups.")
    return merged
