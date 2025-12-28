"""Vector store for code embeddings and semantic search."""

from pathlib import Path
from typing import List, Dict, Optional, Tuple
import hashlib

try:
    import numpy as np
    from langchain_community.vectorstores import FAISS
    from langchain_community.embeddings import OpenAIEmbeddings
    from langchain_core.documents import Document
except ImportError:
    # Fallback for missing dependencies
    FAISS = None
    OpenAIEmbeddings = None
    Document = None


class CodeVectorStore:
    """Vector store for semantic code search."""
    
    def __init__(
        self,
        repo_path: str,
        embedding_model: str = "text-embedding-3-small"
    ):
        """Initialize vector store.
        
        Args:
            repo_path: Path to repository
            embedding_model: OpenAI embedding model name
        """
        self.repo_path = Path(repo_path)
        
        if OpenAIEmbeddings is None:
            raise ImportError(
                "langchain-community required. Install: pip install langchain-community"
            )
        
        self.embeddings = OpenAIEmbeddings(model=embedding_model)
        self.vectorstore: Optional[FAISS] = None
        self.documents: List[Document] = []
    
    def chunk_code_file(
        self,
        file_path: Path,
        chunk_size: int = 500,
        overlap: int = 50
    ) -> List[Dict[str, str]]:
        """Chunk code file for embedding.
        
        Args:
            file_path: Path to file
            chunk_size: Max characters per chunk
            overlap: Overlap between chunks
            
        Returns:
            List of dicts with 'content', 'metadata'
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return []
        
        chunks = []
        lines = content.split('\n')
        
        current_chunk = []
        current_size = 0
        
        for i, line in enumerate(lines):
            line_size = len(line) + 1  # +1 for newline
            
            if current_size + line_size > chunk_size and current_chunk:
                # Save chunk
                chunk_text = '\n'.join(current_chunk)
                chunks.append({
                    'content': chunk_text,
                    'metadata': {
                        'file': str(file_path.relative_to(self.repo_path)),
                        'start_line': i - len(current_chunk) + 1,
                        'end_line': i,
                        'chunk_id': hashlib.md5(chunk_text.encode()).hexdigest()[:8]
                    }
                })
                
                # Keep overlap
                overlap_lines = int(overlap / (current_size / len(current_chunk))) if current_chunk else 0
                current_chunk = current_chunk[-overlap_lines:] if overlap_lines > 0 else []
                current_size = sum(len(l) + 1 for l in current_chunk)
            
            current_chunk.append(line)
            current_size += line_size
        
        # Add final chunk
        if current_chunk:
            chunk_text = '\n'.join(current_chunk)
            chunks.append({
                'content': chunk_text,
                'metadata': {
                    'file': str(file_path.relative_to(self.repo_path)),
                    'start_line': len(lines) - len(current_chunk) + 1,
                    'end_line': len(lines),
                    'chunk_id': hashlib.md5(chunk_text.encode()).hexdigest()[:8]
                }
            })
        
        return chunks
    
    def index_repository(
        self,
        include_tests: bool = True,
        file_extensions: List[str] = ['.py']
    ):
        """Index all code files in repository.
        
        Args:
            include_tests: Whether to include test files
            file_extensions: File extensions to index
        """
        self.documents = []
        
        # Find all matching files
        for ext in file_extensions:
            files = list(self.repo_path.rglob(f'*{ext}'))
            
            for file_path in files:
                # Skip tests if needed
                if not include_tests and ('test' in file_path.name.lower() or 'tests' in str(file_path).lower()):
                    continue
                
                # Skip common directories
                if any(skip in str(file_path) for skip in ['.git', '__pycache__', 'venv', 'node_modules']):
                    continue
                
                # Chunk file
                chunks = self.chunk_code_file(file_path)
                
                for chunk in chunks:
                    doc = Document(
                        page_content=chunk['content'],
                        metadata=chunk['metadata']
                    )
                    self.documents.append(doc)
        
        # Create vector store
        if self.documents:
            self.vectorstore = FAISS.from_documents(
                self.documents,
                self.embeddings
            )
    
    def search(
        self,
        query: str,
        k: int = 5,
        filter_dict: Optional[Dict] = None
    ) -> List[Tuple[Document, float]]:
        """Semantic search for code.
        
        Args:
            query: Search query
            k: Number of results
            filter_dict: Metadata filter
            
        Returns:
            List of (Document, score) tuples
        """
        if self.vectorstore is None:
            return []
        
        return self.vectorstore.similarity_search_with_score(
            query,
            k=k,
            filter=filter_dict
        )
    
    def search_by_symbol(
        self,
        symbol_name: str,
        k: int = 10
    ) -> List[Document]:
        """Find code chunks mentioning a symbol.
        
        Args:
            symbol_name: Function/class/variable name
            k: Number of results
            
        Returns:
            List of relevant Documents
        """
        if self.vectorstore is None:
            return []
        
        # Search with symbol name
        results = self.vectorstore.similarity_search(
            f"usage of {symbol_name} function method class",
            k=k
        )
        
        # Filter to only chunks that actually contain the symbol
        filtered = [
            doc for doc in results
            if symbol_name in doc.page_content
        ]
        
        return filtered
    
    def save(self, path: str):
        """Save vector store to disk.
        
        Args:
            path: Directory path to save to
        """
        if self.vectorstore:
            self.vectorstore.save_local(path)
    
    def load(self, path: str):
        """Load vector store from disk.
        
        Args:
            path: Directory path to load from
        """
        if FAISS and self.embeddings:
            self.vectorstore = FAISS.load_local(
                path,
                self.embeddings,
                allow_dangerous_deserialization=True
            )


class HybridSearch:
    """Combines vector search with keyword search (BM25)."""
    
    def __init__(self, vector_store: CodeVectorStore):
        """Initialize hybrid search.
        
        Args:
            vector_store: CodeVectorStore instance
        """
        self.vector_store = vector_store
        self.bm25_index: Optional[any] = None
        
        try:
            from rank_bm25 import BM25Okapi
            self.BM25 = BM25Okapi
        except ImportError:
            self.BM25 = None
    
    def build_bm25_index(self):
        """Build BM25 keyword index."""
        if self.BM25 is None:
            return
        
        # Tokenize documents
        tokenized_docs = [
            doc.page_content.lower().split()
            for doc in self.vector_store.documents
        ]
        
        self.bm25_index = self.BM25(tokenized_docs)
    
    def search(
        self,
        query: str,
        k: int = 5,
        alpha: float = 0.5
    ) -> List[Document]:
        """Hybrid search combining BM25 and vector search.
        
        Args:
            query: Search query
            k: Number of results
            alpha: Weight for vector search (1-alpha for BM25)
            
        Returns:
            List of top Documents
        """
        # Vector search
        vector_results = self.vector_store.search(query, k=k*2)
        
        # BM25 search
        bm25_scores = {}
        if self.bm25_index:
            query_tokens = query.lower().split()
            scores = self.bm25_index.get_scores(query_tokens)
            
            for i, score in enumerate(scores):
                if i < len(self.vector_store.documents):
                    bm25_scores[i] = score
        
        # Combine scores
        combined_scores = {}
        
        for doc, vec_score in vector_results:
            doc_idx = self.vector_store.documents.index(doc)
            bm25_score = bm25_scores.get(doc_idx, 0.0)
            
            # Normalize and combine
            combined = alpha * (1.0 / (1.0 + vec_score)) + (1 - alpha) * bm25_score
            combined_scores[doc_idx] = (combined, doc)
        
        # Sort and return top k
        sorted_results = sorted(
            combined_scores.values(),
            key=lambda x: x[0],
            reverse=True
        )
        
        return [doc for _, doc in sorted_results[:k]]
