# 🥗 MacroChef Ops

Agentic meal planner for a fictional meal-delivery company. Reads client profiles, dietary restrictions, and macro targets from a synthetic operational database, then builds personalized one-day meal plans with deterministic allergen screening and macro validation. All nutrition-science claims are grounded via RAG over the official *Dietary Guidelines for Americans* with page-level citations.

**Built for:** LLM/AI Engineering portfolio — demonstrates from-scratch tool calling, RAG, deterministic validators, and eval-driven development.

---

## Architecture

| Component | Tech | Purpose |
|-----------|------|---------|
| LLM Client | OpenAI-compatible (Ollama local / Groq deployed) | Unified interface, swap provider via env var |
| Ops Database | SQLite snapshot (synthetic Faker data) | Reproducible, no live Airtable needed for demos |
| RAG Pipeline | ChromaDB + all-MiniLM-L6-v2 | PDF chunking, embedding, cited retrieval |
| Agent Loop | From-scratch tool calling (no framework) | 5 tools, error feedback, step cap |
| Validators | Deterministic Python functions | Macro math + allergen screening (not LLM) |
| UI | Streamlit | Client picker, chat, tool-call transparency |

---

## How it works

1. **Profile** → `get_client_profile` fetches diet, allergies, targets from SQLite
2. **Search** → `search_meals` queries the catalog, excluding allergens via keyword expansion ("dairy" catches paneer/cheddar/yogurt)
3. **Compute** → `compute_plan_macros` adds calories/protein with code, not the LLM
4. **Validate** → `check_plan_against_targets` verifies ±10% macro tolerance and zero allergen violations
5. **Ground** → `lookup_nutrition_guidance` retrieves cited excerpts from the DGA PDF

---

## Evals

| Metric | Result |
|--------|--------|
| Retrieval hit@5 | 3/10 (0.30) |
| Retrieval MRR | 0.092 |
| Agent plan pass rate | 2/4 (50%) |
| Allergen violations | 0 (deterministic) |

*Agent eval run on local qwen3:8b. The 8B model occasionally skips PLAN_JSON formatting on complex multi-tool flows. Production deployments would use a 70B model (Groq) for reliable tool adherence.*

---

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/YOUR_USERNAME/macrochef-ops.git
cd macrochef-ops
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
# source .venv/bin/activate  # Mac/Linux
pip install -r requirements.txt

# 2. Generate offline snapshot (no Airtable needed)
python -m src.snapshot_airtable --offline
python -m src.ingest_docs

# 3. Run CLI agent
python -m src.agent --verbose

# 4. Or run Streamlit UI
streamlit run src/app.py
