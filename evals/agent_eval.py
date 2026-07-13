"""Agent eval: run the agent on realistic scenarios and check outputs.
Run:  python -m evals.agent_eval
"""
import json
import re

from src.agent import SYSTEM, run_agent

PLAN_RE = re.compile(r'PLAN_JSON:\s*(\{.*?\})', re.DOTALL)


def client_scenarios():
    """4 realistic planning scenarios (reduced from 8 for speed)."""
    return [
        {
            "name": "Normal plan for allergy client CL-1002",
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": "Plan tomorrow's meals for client CL-1002."}
            ],
            "checks": ["PLAN_JSON", "allergen_free", "vegetarian"]
        },
        {
            "name": "Override protein target",
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": "Plan tomorrow's meals for client CL-1002. Make it higher protein - 180g."}
            ],
            "checks": ["PLAN_JSON", "high_protein"]
        },
        {
            "name": "Nutrition question (no plan)",
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": "Why does protein matter for muscle?"}
            ],
            "checks": ["no_plan", "citation"]
        },
        {
            "name": "Implausible targets (should refuse)",
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": "Plan a day with 800 calories and 250g protein for CL-1002."}
            ],
            "checks": ["no_plan", "refuses"]
        },
    ]


def check_plan_json(text):
    return bool(PLAN_RE.search(text or ""))


def check_allergen_free(text):
    return "allergen" in (text or "").lower() and "violation" not in (text or "").lower()


def check_high_protein(text):
    return "180" in (text or "") or "protein" in (text or "").lower()


def check_citation(text):
    return "dga_2020-2025.pdf" in (text or "")


def check_refuses(text):
    return "implausible" in (text or "").lower() or "realistic" in (text or "").lower()


CHECK_MAP = {
    "PLAN_JSON": check_plan_json,
    "allergen_free": check_allergen_free,
    "vegetarian": lambda t: "vegetarian" in t.lower() if t else False,
    "high_protein": check_high_protein,
    "no_plan": lambda t: not check_plan_json(t),
    "citation": check_citation,
    "refuses": check_refuses,
}


def run_scenario(sc):
    print(f"\n{'='*60}")
    print(f"SCENARIO: {sc['name']}")
    print(f"{'='*60}")
    out = run_agent(sc["messages"], verbose=False)
    final = out[-1].get("content", "")
    
    # Print truncated final answer
    print(f"\n>>> FINAL ANSWER (truncated):\n{final[:400]}...\n")
    
    results = {}
    for check in sc["checks"]:
        passed = CHECK_MAP[check](final)
        results[check] = passed
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {check}")
    
    overall = all(results.values())
    print(f"\n  OVERALL: {'PASS' if overall else 'FAIL'}")
    return overall


def main():
    scenarios = client_scenarios()
    passed = sum(run_scenario(s) for s in scenarios)
    total = len(scenarios)
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{total} scenarios passed ({passed/total:.0%})")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()