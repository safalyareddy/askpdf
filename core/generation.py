import logging
from typing import List, Dict, Any, Optional
import httpx
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.language_models.llms import LLM
from langchain_ollama import OllamaLLM

from core.retrieval import QueryIntent

logger = logging.getLogger("documind.generation")

# =====================================================================
# Specialized System Prompts
# =====================================================================

QA_PROMPT_TEMPLATE = """You are DocuMind AI, an intelligent, precise enterprise document intelligence assistant.
Answer the user's question accurately using ONLY the retrieved context passages below.
If the context does not contain enough information to answer the question, state clearly what information is available and what is missing, rather than guessing.
Provide a clear, well-structured response using Markdown formatting (headings, bullet points, and bold text).

Retrieved Context:
---------------------
{context}
---------------------

User Question: {question}

Detailed Grounded Answer:"""

ABSTRACT_PROMPT_TEMPLATE = """You are DocuMind AI. The user is asking for the Abstract of the document.
Your task is to present the ACTUAL CONTENT and full narrative of the Abstract from the retrieved passages below.
DO NOT merely state where the abstract is located or what page number it is on. Provide the full text, problem statement, methodology, and solution described in the Abstract.

Retrieved Context:
---------------------
{context}
---------------------

Question: {question}

Full Abstract Content:"""

SUMMARIZATION_PROMPT_TEMPLATE = """You are DocuMind AI. The user has requested a comprehensive summary of the document.
Synthesize the provided passages across the entire document into an in-depth, professional summary.
Format your answer with clear Markdown sections:
### 1. Executive Overview & Objectives
### 2. Problem Statement & Motivation
### 3. Core Solution, Architecture & Key Features
### 4. Implementation Details & Tools Used
### 5. Scope, Limitations & Future Work

Retrieved Context:
---------------------
{context}
---------------------

Document Summary Request: {question}

Comprehensive Document Summary:"""

COMPARISON_PROMPT_TEMPLATE = """You are DocuMind AI. The user has requested a comparative analysis between documents.
Using ONLY the provided passages, compare and contrast the projects, methodologies, and findings.
Structure your answer clearly:
### 1. Overview of Each Document
### 2. Key Architectural & Methodology Differences
### 3. Similarities & Common Themes
### 4. Comparative Evaluation & Summary

Retrieved Context:
---------------------
{context}
---------------------

Comparison Request: {question}

Comparative Analysis:"""


class OpenAILikeLLM(LLM):
    """Universal OpenAI-compatible chat completions wrapper (Groq, Together, OpenAI)."""
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "llama-3.3-70b-versatile"
    temperature: float = 0.1
    timeout_sec: float = 90.0

    @property
    def _llm_type(self) -> str:
        return "openai_compatible"

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any) -> str:
        clean_base = self.base_url.strip().rstrip("/")
        url = clean_base if clean_base.endswith("/chat/completions") else f"{clean_base}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"

        candidate_models = [self.model]
        if "groq.com" in clean_base:
            for fallback in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
                if fallback not in candidate_models:
                    candidate_models.append(fallback)

        last_error = None
        for candidate in candidate_models:
            payload = {
                "model": candidate,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.temperature
            }
            try:
                with httpx.Client(timeout=self.timeout_sec) as client:
                    res = client.post(url, json=payload, headers=headers)
                    if res.status_code == 200:
                        return res.json()["choices"][0]["message"]["content"]
                    last_error = f"HTTP {res.status_code} ({res.text})"
                    if res.status_code == 404 and candidate != candidate_models[-1]:
                        continue
                    break
            except Exception as e:
                last_error = str(e)
                break

        raise RuntimeError(f"Hosted LLM error: {last_error}")


class GenerationEngine:
    def __init__(self, llm: Any):
        self.llm = llm
        self.qa_prompt = PromptTemplate(template=QA_PROMPT_TEMPLATE, input_variables=["context", "question"])
        self.abstract_prompt = PromptTemplate(template=ABSTRACT_PROMPT_TEMPLATE, input_variables=["context", "question"])
        self.summary_prompt = PromptTemplate(template=SUMMARIZATION_PROMPT_TEMPLATE, input_variables=["context", "question"])
        self.comparison_prompt = PromptTemplate(template=COMPARISON_PROMPT_TEMPLATE, input_variables=["context", "question"])

    def format_citations(self, documents: List[Document]) -> List[Dict[str, Any]]:
        """
        Formats precise citations distinguishing physical PDF page from printed page.
        Example: '23MIS0125_ListLocal_Safalya.pdf — PDF page 4 (printed page 3)'
        """
        citations = []
        seen_keys = set()

        for doc in documents:
            meta = doc.metadata or {}
            source = meta.get("source", meta.get("document_name", "Unknown Document"))
            phys_page = meta.get("physical_page_number", meta.get("page", 1))
            printed_page = meta.get("printed_page_number", "")
            content = doc.page_content.strip()

            # Construct citation label
            if printed_page and str(printed_page).strip():
                label = f"{source} — PDF page {phys_page} (printed page {printed_page})"
            else:
                label = f"{source} — PDF page {phys_page}"

            dedup_key = (source, phys_page, str(printed_page))
            if dedup_key not in seen_keys:
                seen_keys.add(dedup_key)
                citations.append({
                    "source": source,
                    "document_name": source,
                    "physical_page": phys_page,
                    "page": phys_page,
                    "printed_page": printed_page,
                    "citation_label": label,
                    "snippet": content
                })

        return citations

    def generate_response(
        self,
        query: str,
        context_docs: List[Document],
        intent: QueryIntent = QueryIntent.FACTUAL_QA
    ) -> Dict[str, Any]:
        """Assembles prompt according to query intent, invokes LLM, and attaches citations."""
        citations = self.format_citations(context_docs)

        if not context_docs:
            return {
                "answer": "I could not find any relevant information in the indexed documents to answer this question.",
                "sources": []
            }

        # Build context string
        context_parts = []
        for doc in context_docs:
            meta = doc.metadata or {}
            src = meta.get("source", "Document")
            p_phys = meta.get("physical_page_number", meta.get("page", 1))
            p_print = meta.get("printed_page_number", "")
            page_info = f"Physical Page {p_phys}" + (f", Printed Page {p_print}" if p_print else "")
            context_parts.append(f"[{src} | {page_info}]\n{doc.page_content.strip()}")

        formatted_context = "\n\n".join(context_parts)

        # Select appropriate prompt template
        if intent == QueryIntent.ABSTRACT:
            prompt = self.abstract_prompt.format(context=formatted_context, question=query)
        elif intent == QueryIntent.SUMMARIZATION:
            prompt = self.summary_prompt.format(context=formatted_context, question=query)
        elif intent == QueryIntent.COMPARISON:
            prompt = self.comparison_prompt.format(context=formatted_context, question=query)
        else:
            prompt = self.qa_prompt.format(context=formatted_context, question=query)

        try:
            raw_response = self.llm.invoke(prompt)
            answer_text = raw_response.strip() if isinstance(raw_response, str) else str(raw_response).strip()
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            err = str(e).lower()
            if "connection refused" in err or "connect" in err:
                return {
                    "answer": "Unable to connect to model service. Please verify that Ollama is active (`ollama serve`).",
                    "sources": citations
                }
            elif "timed out" in err or "timeout" in err:
                return {
                    "answer": "The language model timed out while synthesizing the answer. Please try again with a more specific query.",
                    "sources": citations
                }
            return {
                "answer": f"Language model error: {str(e)}",
                "sources": citations
            }

        return {
            "answer": answer_text,
            "sources": citations
        }
