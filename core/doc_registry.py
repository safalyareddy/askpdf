import os
import json
import hashlib
import logging
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger("documind.registry")

def get_registry_path() -> str:
    persist_dir = os.getenv("PERSIST_DIR", "./db")
    if persist_dir.startswith("/app") and not os.path.exists("/app"):
        persist_dir = "./db"
    return os.path.join(persist_dir, "documents_registry.json")


REGISTRY_PATH = get_registry_path()


def _generate_doc_id(filename: str) -> str:
    """Generates a stable document ID from filename."""
    h = hashlib.sha256(filename.encode("utf-8")).hexdigest()[:10]
    return f"doc_{h}"


class DocumentRegistry:
    def __init__(self, registry_file: Optional[str] = None):
        self.registry_file = registry_file or get_registry_path()
        self.documents: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self):
        """Loads document registry from disk."""
        if os.path.exists(self.registry_file):
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.documents = data
            except Exception as e:
                logger.warning(f"Failed to load registry from {self.registry_file}: {e}")
                self.documents = {}
        else:
            self.documents = {}

    def save(self):
        """Persists document registry to disk."""
        os.makedirs(os.path.dirname(self.registry_file), exist_ok=True)
        try:
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump(self.documents, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save registry to {self.registry_file}: {e}")

    def register(
        self,
        filename: str,
        pages: int,
        chunks: int,
        size_kb: float,
        printed_pages: Optional[Dict[int, str]] = None,
        sections: Optional[List[str]] = None,
        display_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Registers or updates a document in the persistent registry."""
        doc_id = _generate_doc_id(filename)

        # Retain existing upload order and timestamp if updating
        existing = self.documents.get(filename)
        if existing:
            upload_order = existing.get("upload_order", len(self.documents))
            upload_time = existing.get("upload_time", datetime.utcnow().isoformat())
        else:
            upload_order = len(self.documents) + 1
            upload_time = datetime.utcnow().isoformat()

        clean_display = display_name or filename.replace("_", " ").replace(".pdf", "")

        serialized_printed = {str(k): v for k, v in (printed_pages or {}).items()}

        doc_entry = {
            "document_id": doc_id,
            "filename": filename,
            "display_name": clean_display,
            "upload_order": upload_order,
            "upload_time": upload_time,
            "pages": pages,
            "chunks": chunks,
            "size_kb": size_kb,
            "printed_pages": serialized_printed,
            "sections": sections or []
        }

        self.documents[filename] = doc_entry
        self.save()
        return doc_entry

    def remove(self, filename: str) -> bool:
        """Removes a document from the registry and normalizes upload orders."""
        if filename in self.documents:
            del self.documents[filename]
            # Normalize upload orders
            sorted_docs = sorted(self.documents.values(), key=lambda x: x.get("upload_order", 0))
            for idx, doc in enumerate(sorted_docs):
                doc["upload_order"] = idx + 1
                self.documents[doc["filename"]] = doc
            self.save()
            return True
        return False

    def get_all(self) -> List[Dict[str, Any]]:
        """Returns all documents sorted by upload order."""
        return sorted(self.documents.values(), key=lambda x: x.get("upload_order", 999))

    def get_by_name(self, filename: str) -> Optional[Dict[str, Any]]:
        return self.documents.get(filename)

    def get_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        for doc in self.documents.values():
            if doc.get("document_id") == doc_id:
                return doc
        return None

    def resolve_ordinal(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Resolves phrases like 'first document', '1st document', 'second document'
        to a specific document based on stable upload order.
        """
        q_lower = query.lower()
        all_docs = self.get_all()
        if not all_docs:
            return None

        # Check for first document
        if any(w in q_lower for w in ["first document", "1st document", "document 1", "first pdf", "1st pdf", "doc 1"]):
            return all_docs[0] if len(all_docs) >= 1 else None

        # Check for second document
        if any(w in q_lower for w in ["second document", "2nd document", "document 2", "second pdf", "2nd pdf", "doc 2"]):
            return all_docs[1] if len(all_docs) >= 2 else None

        # Check for third document
        if any(w in q_lower for w in ["third document", "3rd document", "document 3", "third pdf", "3rd pdf", "doc 3"]):
            return all_docs[2] if len(all_docs) >= 3 else None

        # Check for last document
        if any(w in q_lower for w in ["last document", "last pdf", "final document"]):
            return all_docs[-1] if all_docs else None

        return None

    def reconcile_with_disk(self, pdf_dir: str):
        """Purges any registry entries whose files no longer exist on disk."""
        if not os.path.exists(pdf_dir):
            return
        disk_files = set(os.listdir(pdf_dir))
        removed = []
        for fn in list(self.documents.keys()):
            if fn not in disk_files:
                del self.documents[fn]
                removed.append(fn)
        if removed:
            # Renumber upload orders
            sorted_docs = sorted(self.documents.values(), key=lambda x: x.get("upload_order", 0))
            for idx, doc in enumerate(sorted_docs):
                doc["upload_order"] = idx + 1
                self.documents[doc["filename"]] = doc
            self.save()
            logger.info(f"Reconciled registry with disk: removed {removed}")

    def find_mentioned_document(self, query: str) -> Optional[Dict[str, Any]]:
        """Identifies if a specific document is mentioned in the query text."""
        q_lower = query.lower()
        all_docs = self.get_all()

        # Pass 1: Check for exact filename or base filename matches first
        for doc in all_docs:
            fn = doc["filename"].lower()
            fn_no_ext = fn.replace(".pdf", "")
            if fn in q_lower or fn_no_ext in q_lower:
                return doc

        # Pass 2: Check distinctive project name tokens (excluding generic terms and student IDs)
        generic_tokens = {"assignment", "report", "project", "lab", "document", "paper", "presentation"}
        for doc in all_docs:
            fn_no_ext = doc["filename"].lower().replace(".pdf", "")
            tokens = [
                t for t in re.split(r"[_\s-]+", fn_no_ext)
                if len(t) >= 4 and not re.match(r"^\d+[a-z]+\d+$", t) and not t.isdigit() and t not in generic_tokens
            ]
            for token in tokens:
                if token in q_lower:
                    return doc

        return None


# Global registry singleton
registry = DocumentRegistry()
