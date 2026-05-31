# rag_module/__init__.py
# SurgiMind RAG + LLM Reasoning Package
#
# Public API:
#   from rag_module.rag_engine    import retrieve_protocols, retrieve_for_ml_output, build_index
#   from rag_module.llm_reasoning import generate_report, detect_red_flags

from rag_module.rag_engine    import retrieve_protocols, retrieve_for_ml_output, build_index
from rag_module.llm_reasoning import generate_report, detect_red_flags

__all__ = [
    "retrieve_protocols",
    "retrieve_for_ml_output",
    "build_index",
    "generate_report",
    "detect_red_flags",
]