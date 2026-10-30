import re
import logging
from enum import Enum
from typing import List, Dict, Any, Tuple, Optional
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma

from core.doc_registry import registry, DocumentRegistry

logger = logging.getLogger("documind.retrieval")


class QueryIntent(str, Enum):
    ABSTRACT = "abstract"
    SUMMARIZATION = "summarization"
    COMPARISON = "comparison"
    SECTION_EXTRACTION = "section_extraction"
    FACTUAL_QA = "factual_qa"


def classify_query_intent(query: str) -> QueryIntent:
    """Classifies the semantic intent of the user's question."""
    q_clean = query.lower().strip()

    # Comparison intent
    if any(k in q_clean for k in ["compare", "comparison", "difference between", "differences between", "both documents", "both reports"]):
        return QueryIntent.COMPARISON

    # Abstract intent
    if re.search(r"\b(?:abstract|executive\s+summary)\b", q_clean):
        return QueryIntent.ABSTRACT

    # Summarization intent
    if any(k in q_clean for k in ["summarize", "summary", "give an overview", "brief overview", "what is this report about", "what is this document about"]):
        return QueryIntent.SUMMARIZATION

    # Section extraction intent
    if any(k in q_clean for k in ["implementation section", "limitations section", "methodology section", "architecture section", "user flow section"]):
        return QueryIntent.SECTION_EXTRACTION

    return QueryIntent.FACTUAL_QA


class RetrievalEngine:
    def __init__(self, vectorstore: Optional[Chroma], doc_registry: DocumentRegistry = registry):
        self.vectorstore = vectorstore
        self.registry = doc_registry

    def resolve_document_scope(
        self,
        query: str,
        session_selected_doc: Optional[str] = None
    ) -> Tuple[Optional[Dict[str, Any]], bool, bool]:
        """
        Resolves which document the query targets.
        Returns: (resolved_doc_entry, is_multi_doc_query, is_ambiguous)
        """
        all_docs = self.registry.get_all()
        if not all_docs:
            return None, False, False

        # If only 1 document is indexed, always target it
        if len(all_docs) == 1:
            return all_docs[0], False, False

        q_lower = query.lower()

        # 1. Check for explicit cross-document requests
        if any(w in q_lower for w in ["both documents", "all documents", "both pdfs", "compare the documents"]):
            return None, True, False

        # 2. Check for explicit document name in query
        mentioned_doc = self.registry.find_mentioned_document(query)
        if mentioned_doc:
            return mentioned_doc, False, False

        # 3. Check for ordinal reference ("first document", "second document")
        ordinal_doc = self.registry.resolve_ordinal(query)
        if ordinal_doc:
            return ordinal_doc, False, False

        # 4. Check session's previously selected document
        if session_selected_doc:
            if session_selected_doc == "all":
                return None, True, False
            doc_by_name = self.registry.get_by_name(session_selected_doc)
            if doc_by_name:
                return doc_by_name, False, False
            doc_by_id = self.registry.get_by_id(session_selected_doc)
            if doc_by_id:
                return doc_by_id, False, False

        # 5. Check if query requires single document scope (e.g. abstract or full summary) without naming it
        intent = classify_query_intent(query)
        if intent in [QueryIntent.ABSTRACT, QueryIntent.SUMMARIZATION] and not session_selected_doc:
            # Ambiguous: user asked for summary/abstract of an unspecified document
            return None, False, True

        # Default: Search across all documents if specific target not required
        return None, True, False

    def retrieve_abstract_chunks(self, target_doc: Dict[str, Any]) -> List[Document]:
        """
        Retrieves the genuine Abstract text chunks for a document, strictly avoiding
        Table of Contents and Index listings.
        """
        if not self.vectorstore:
            return []

        filename = target_doc["filename"]
        logger.info(f"Retrieving substantive Abstract chunks for '{filename}'...")

        # 1. Direct section retrieval: lookup chunks tagged with section_heading 'Abstract' and is_toc=False
        try:
            coll = getattr(self.vectorstore, "_collection", None)
            if coll:
                direct = coll.get(
                    where={
                        "$and": [
                            {"source": {"$eq": filename}},
                            {"section_heading": {"$eq": "Abstract"}},
                            {"is_toc": {"$eq": False}}
                        ]
                    }
                )
                if direct and direct.get("ids") and len(direct["ids"]) > 0:
                    chunks = []
                    for i in range(len(direct["ids"])):
                        chunks.append(
                            Document(
                                page_content=direct["documents"][i],
                                metadata=direct["metadatas"][i]
                            )
                        )
                    logger.info(f"Retrieved {len(chunks)} direct Abstract section chunks for '{filename}'.")
                    return chunks[:5]
        except Exception as e:
            logger.warning(f"Direct section abstract lookup error: {e}")

        # 2. Semantic search with anti-TOC filtering over large candidate window (k=25)
        try:
            results = self.vectorstore.similarity_search(
                f"Abstract problem statement proposed solution {filename}",
                k=25,
                filter={"source": filename}
            )
        except Exception as e:
            logger.warning(f"Chroma filtered search failed, falling back: {e}")
            results = self.vectorstore.similarity_search("Abstract overview problem solution", k=20)

        # Filter out Table of Contents chunks
        content_chunks = []
        for doc in results:
            meta = doc.metadata or {}
            is_toc = meta.get("is_toc", False)
            content = doc.page_content.strip()

            # Disregard TOC lines (e.g. 'Abstract ............... 3')
            if is_toc or len(re.findall(r"\.{3,}", content)) >= 2:
                continue

            # Prioritize chunks on early pages (pages 1 to 5) or matching section heading
            sec = str(meta.get("section_heading", "")).lower()
            phys_page = meta.get("physical_page_number", meta.get("page", 99))
            if "abstract" in sec or "abstract" in content.lower() or phys_page <= 5:
                content_chunks.append(doc)

        if content_chunks:
            return content_chunks[:5]

        # Fallback: return early non-TOC page chunks
        early_chunks = [d for d in results if not d.metadata.get("is_toc", False) and d.metadata.get("page", 99) in [2, 3, 4]]
        return early_chunks[:4] if early_chunks else results[:3]

    def retrieve_summary_chunks(self, target_doc: Dict[str, Any]) -> List[Document]:
        """
        Retrieves representative structural chunks across the entire document
        (Abstract/Intro on early pages, Architecture/Core in middle, Conclusion/Limits at end).
        """
        if not self.vectorstore:
            return []

        filename = target_doc["filename"]
        total_pages = target_doc.get("pages", 10)
        logger.info(f"Assembling structural summary passages across {total_pages} pages for '{filename}'...")

        summary_chunks: List[Document] = []
        seen_pages = set()

        # 1. Retrieve Abstract / Intro passages
        abstract_chunks = self.retrieve_abstract_chunks(target_doc)
        for c in abstract_chunks[:2]:
            p = c.metadata.get("physical_page_number", c.metadata.get("page", 0))
            if p not in seen_pages:
                seen_pages.add(p)
                summary_chunks.append(c)

        # 2. Retrieve middle-section methodology / implementation passages
        try:
            mid_results = self.vectorstore.similarity_search(
                f"implementation architecture features solution {filename}",
                k=6,
                filter={"source": filename}
            )
            for c in mid_results:
                meta = c.metadata or {}
                if meta.get("is_toc", False):
                    continue
                p = meta.get("physical_page_number", meta.get("page", 0))
                if p not in seen_pages and 4 <= p <= (total_pages - 3):
                    seen_pages.add(p)
                    summary_chunks.append(c)
                    if len(summary_chunks) >= 4:
                        break
        except Exception as e:
            logger.warning(f"Error retrieving middle summary chunks: {e}")

        # 3. Retrieve concluding remarks / scope & limitations
        try:
            end_results = self.vectorstore.similarity_search(
                f"conclusion limitations scope future work {filename}",
                k=4,
                filter={"source": filename}
            )
            for c in end_results:
                meta = c.metadata or {}
                if meta.get("is_toc", False):
                    continue
                p = meta.get("physical_page_number", meta.get("page", 0))
                if p not in seen_pages:
                    seen_pages.add(p)
                    summary_chunks.append(c)
                    if len(summary_chunks) >= 6:
                        break
        except Exception as e:
            logger.warning(f"Error retrieving concluding summary chunks: {e}")

        return summary_chunks if summary_chunks else abstract_chunks

    def retrieve_comparison_chunks(self, query: str) -> List[Document]:
        """Retrieves key passages from each indexed document for balanced cross-document comparison."""
        if not self.vectorstore:
            return []

        all_docs = self.registry.get_all()
        comparison_chunks: List[Document] = []

        for doc_entry in all_docs[:2]:  # Compare top 2 documents
            fn = doc_entry["filename"]
            try:
                results = self.vectorstore.similarity_search(
                    query,
                    k=4,
                    filter={"source": fn}
                )
                valid = [d for d in results if not d.metadata.get("is_toc", False)]
                comparison_chunks.extend(valid[:3])
            except Exception as e:
                logger.warning(f"Error in comparison retrieval for {fn}: {e}")

        return comparison_chunks

    def retrieve_relevant_chunks(
        self,
        query: str,
        target_doc: Optional[Dict[str, Any]] = None,
        intent: QueryIntent = QueryIntent.FACTUAL_QA,
        top_k: int = 5
    ) -> List[Document]:
        """General retrieval pipeline with query routing and anti-TOC filtering."""
        if not self.vectorstore:
            return []

        # Route specialized intents
        if intent == QueryIntent.ABSTRACT and target_doc:
            return self.retrieve_abstract_chunks(target_doc)

        if intent == QueryIntent.SUMMARIZATION and target_doc:
            return self.retrieve_summary_chunks(target_doc)

        if intent == QueryIntent.COMPARISON:
            return self.retrieve_comparison_chunks(query)

        # Standard semantic retrieval with optional document filter
        filter_dict = {"source": target_doc["filename"]} if target_doc else None

        try:
            if filter_dict:
                candidates = self.vectorstore.similarity_search(query, k=top_k * 2, filter=filter_dict)
            else:
                candidates = self.vectorstore.similarity_search(query, k=top_k * 2)
        except Exception as e:
            logger.warning(f"Similarity search error: {e}, attempting unfiltered fallback...")
            candidates = self.vectorstore.similarity_search(query, k=top_k * 2)

        # Filter out Table of Contents and duplicate snippets
        filtered: List[Document] = []
        seen_snippets = set()

        for doc in candidates:
            meta = doc.metadata or {}
            content = doc.page_content.strip()

            # Anti-TOC guardrail
            if meta.get("is_toc", False) or len(re.findall(r"\.{3,}", content)) >= 2:
                continue

            # Deduplication
            snippet_key = content[:100].lower()
            if snippet_key in seen_snippets:
                continue
            seen_snippets.add(snippet_key)

            filtered.append(doc)
            if len(filtered) >= top_k:
                break

        return filtered if filtered else candidates[:top_k]
