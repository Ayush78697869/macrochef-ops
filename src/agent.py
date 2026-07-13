"""The agent: tool schemas, system prompt, the tool-calling loop, and a CLI REPL.
Run:  python -m src.agent --verbose
"""
import json

from src import tools
from src.llm import extra_opts, get_client, strip_think

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "get_client_profile",
        "description": "Fetch a client's diet, allergies, and macro targets by "
                       "Client ID (e.g. CL-1003), name, or email.",
        "parameters": {"type": "object", "properties": {
            "name_or_id": {"type": "string"}},
            "required": ["name_or_id"]}}},
    {"type": "function", "function": {
        "name": "search_meals",
        "description": "Search the meal catalog. Returns up to `limit` meals with "
                       "per-serving macros. ALWAYS pass the client's allergies as "
                       "exclude_ingredients when planning for a client.",
        "parameters": {"type": "object", "properties": {
            "min_protein_g": {"type": "number"},
            "max_calories": {"type": "number"},
            "meal_type": {"type": "string",
                          "enum": ["breakfast", "lunch", "dinner", "snack"]},
            "exclude_ingredients": {"type": "array", "items": {"type": "string"},
                                    "description": "allergens/ingredients to avoid"},
            "max_minutes": {"type": "integer"},
            "name_contains": {"type": "string"},
            "sort_by": {"type": "string", "enum": ["rating_desc", "protein_desc",
                                                   "calories_asc", "minutes_asc"]},
            "limit": {"type": "integer"}},
            "required": []}}},
    {"type": "function", "function": {
        "name": "lookup_nutrition_guidance",
        "description": "Look up nutrition science in the Dietary Guidelines corpus. "
                       "Returns cited excerpts. Use for any health/science claim.",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string"}},
            "required": ["question"]}}},
    {"type": "function", "function": {
        "name": "compute_plan_macros",
        "description": "Compute exact macro totals for a list of meal ids.",
        "parameters": {"type": "object", "properties": {
            "meal_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["meal_ids"]}}},
    {"type": "function", "function": {
        "name": "check_plan_against_targets",
        "description": "Deterministically check a plan: macro targets (default "
                       "+/-10%) AND allergen screening. ALWAYS call before "
                       "presenting a plan.",
        "parameters": {"type": "object", "properties": {
            "meal_ids": {"type": "array", "items": {"type": "string"}},
            "targets": {"type": "object", "properties": {
                "calories": {"type": "number"}, "protein_g": {"type": "number"},
                "carbs_g": {"type": "number"}, "fat_g": {"type": "number"}}},
            "allergies": {"type": "array", "items": {"type": "string"}},
            "tolerance_pct": {"type": "number"}},
            "required": ["meal_ids", "targets"]}}},
]

TOOL_MAP = {
    "get_client_profile": tools.get_client_profile,
    "search_meals": tools.search_meals,
    "lookup_nutrition_guidance": tools.lookup_nutrition_guidance,
    "compute_plan_macros": tools.compute_plan_macros,
    "check_plan_against_targets": tools.check_plan_against_targets,
}

SYSTEM = """You are MacroChef Ops, the meal-planning agent for a meal-delivery \
company. Clients, meals, and orders live in the company database (snapshotted \
from Airtable).

When asked to plan for a client:
1. Call get_client_profile first. Use their calorie/protein targets unless the \
user overrides them, and treat their allergies as hard constraints.
2. Search meals per slot (breakfast/lunch/dinner, snack if needed, ~25/30/35/10% \
of calories), ALWAYS passing the client's allergies as exclude_ingredients. \
Respect their diet (e.g. vegetarian -> avoid meat/fish meals by name and ingredients).
3. Call compute_plan_macros, then check_plan_against_targets WITH the allergies \
list. If it fails, swap meals and re-check (max 3 rounds).
4. Present the plan: each slot with meal name, id, calories, protein; totals vs \
targets; explicitly confirm it is allergen-free.

Rules:
- NEVER invent meals or numbers - only tool results.
- Ground nutrition-science claims via lookup_nutrition_guidance, keep citations.
- If targets are implausible (e.g. 250g protein in 800 kcal), say so and propose \
realistic ones instead of forcing a plan.
- End every final plan with EXACTLY one line:
PLAN_JSON: {"meal_ids": ["rec...", "rec..."], "client_id": "CL-...."}
- Plain nutrition questions: answer with citations, no plan."""


def run_agent(messages, max_steps=12, verbose=False):
    """The loop: model -> tool calls -> results -> model ... until a final answer.
    Malformed/failed tool calls are fed back as errors so the model can retry."""
    client, model = get_client()
    for _ in range(max_steps):
        resp = client.chat.completions.create(
            model=model, temperature=0.2,
            messages=messages, tools=TOOL_SCHEMAS,
            **extra_opts(),
        )
        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            return messages  # final answer reached
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
                result = TOOL_MAP[name](**args)
            except Exception as e:  # malformed args happen on 8B models
                result = {"error": f"{type(e).__name__}: {e}"}
            if verbose:
                print(f"  tool> {name}({tc.function.arguments}) "
                      f"-> {str(result)[:120]}")
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result)})
    messages.append({"role": "assistant", "content":
                     "I hit my step limit - here is my best partial answer. "
                     "Try narrowing the request."})
    return messages


def main():
    import sys
    verbose = "--verbose" in sys.argv
    print("MacroChef Ops REPL - type a request, or 'quit'.")
    messages = [{"role": "system", "content": SYSTEM}]
    while True:
        user = input("\nyou> ").strip()
        if user.lower() in ("quit", "exit", "q"):
            break
        messages.append({"role": "user", "content": user})
        messages = run_agent(messages, verbose=verbose)
        print("\nmacrochef>", strip_think(messages[-1].get("content") or ""))


if __name__ == "__main__":
    main()