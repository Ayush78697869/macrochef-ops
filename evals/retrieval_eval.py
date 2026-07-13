"""Retrieval eval: hit@k and MRR over the hand-written QA set.
Run:  python -m evals.retrieval_eval
"""
import json

from src.retrieval import retrieve


def evaluate(path="evals/retrieval_qa.jsonl", k=5):
    cases = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    hits, rr = 0, 0.0
    for c in cases:
        results = retrieve(c["question"], k=k)
        rank = 0
        for i, r in enumerate(results, 1):
            if r["source"] == c["expected_source"] and r["page"] in c["expected_pages"]:
                rank = i
                break
        hits += bool(rank)
        rr += 1 / rank if rank else 0
        print(f"{'HIT ' if rank else 'MISS'} rank={rank or '-'}  {c['question'][:65]}")
    n = len(cases)
    print(f"\nhit@{k} = {hits}/{n} = {hits/n:.2f}    MRR = {rr/n:.3f}")


if __name__ == "__main__":
    evaluate()
