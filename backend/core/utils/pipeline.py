"""Normalization pipeline for converting raw Notion content to downstream formats."""

from typing import List, Optional
from backend.connectors.notion.notion_models.schemas import ExtractionStats
from backend.connectors.notion.notion_utils.logging_config import get_logger
from backend.core.models.memory_schema import MemoryDocument

logger = get_logger(__name__)


class NormalizationPipeline:
    """
    Processes extracted MemoryDocuments for downstream consumption.
    Handles filtering, deduplication, enrichment, and validation.
    """
    
    def __init__(self):
        self.stats = {
            'input_documents': 0,
            'output_documents': 0,
            'filtered': 0,
            'duplicates_removed': 0,
        }
    
    def process(
        self,
        documents: List[MemoryDocument],
        min_content_length: int = 10,
        remove_duplicates: bool = True,
        enrichment_fn: Optional[callable] = None
    ) -> List[MemoryDocument]:
        """
        Process documents through normalization pipeline.
        
        Args:
            documents: Extracted MemoryDocuments
            min_content_length: Filter out documents with less content
            remove_duplicates: Remove duplicate content
            enrichment_fn: Optional function to enrich documents
        
        Returns:
            Processed documents ready for downstream pipelines
        """
        self.stats['input_documents'] = len(documents)
        
        # Filter by content length
        documents = self._filter_by_content_length(documents, min_content_length)
        
        # Remove duplicates if requested
        if remove_duplicates:
            documents = self._remove_duplicates(documents)
        
        # Enrich if function provided
        if enrichment_fn:
            documents = self._enrich_documents(documents, enrichment_fn)
        
        # Validate
        documents = self._validate_documents(documents)
        
        self.stats['output_documents'] = len(documents)
        
        logger.info(
            "Normalization complete",
            stats=self.stats
        )
        
        return documents
    
    def _filter_by_content_length(
        self,
        documents: List[MemoryDocument],
        min_length: int
    ) -> List[MemoryDocument]:
        """Filter documents by minimum content length."""
        filtered = []
        for doc in documents:
            if len(doc.content or '') >= min_length:
                filtered.append(doc)
            else:
                self.stats['filtered'] += 1
        return filtered
    
    def _remove_duplicates(
        self,
        documents: List[MemoryDocument]
    ) -> List[MemoryDocument]:
        """Remove documents with duplicate content."""
        seen_content = set()
        unique = []
        
        for doc in documents:
            # Use content hash for duplicate detection
            content_hash = hash(doc.content or '')
            if content_hash not in seen_content:
                unique.append(doc)
                seen_content.add(content_hash)
            else:
                self.stats['duplicates_removed'] += 1
        
        return unique
    
    def _enrich_documents(
        self,
        documents: List[MemoryDocument],
        enrichment_fn: callable
    ) -> List[MemoryDocument]:
        """Apply enrichment function to documents."""
        enriched = []
        for doc in documents:
            try:
                enriched_doc = enrichment_fn(doc)
                enriched.append(enriched_doc)
            except Exception as e:
                logger.warning(
                    "Enrichment failed",
                    document_id=doc.id,
                    error=str(e)
                )
                enriched.append(doc)  # Keep original on error
        
        return enriched
    
    def _validate_documents(
        self,
        documents: List[MemoryDocument]
    ) -> List[MemoryDocument]:
        """Validate documents meet required fields."""
        valid = []
        for doc in documents:
            if doc.id and doc.title and doc.content:
                valid.append(doc)
            else:
                logger.warning(
                    "Document failed validation",
                    document_id=doc.id,
                    has_id=bool(doc.id),
                    has_title=bool(doc.title),
                    has_content=bool(doc.content)
                )
        
        return valid


# class DocumentChunker:
#     """Split documents into chunks for embedding."""
    
#     def __init__(
#         self,
#         chunk_size: int = 1000,
#         chunk_overlap: int = 100
#     ):
#         self.chunk_size = chunk_size
#         self.chunk_overlap = chunk_overlap
    
#     def chunk_documents(
#         self,
#         documents: List[MemoryDocument]
#     ) -> List[dict]:
#         """
#         Chunk documents for embedding.
        
#         Args:
#             documents: Processed MemoryDocuments
        
#         Returns:
#             List of chunks with metadata
#         """
#         chunks = []
        
#         for doc in documents:
#             doc_chunks = self._chunk_text(
#                 doc.content or '',
#                 doc.id,
#                 doc.title
#             )
#             chunks.extend(doc_chunks)
        
#         logger.info(
#             "Chunking complete",
#             total_documents=len(documents),
#             total_chunks=len(chunks)
#         )
        
#         return chunks
    
#     def _chunk_text(
#         self,
#         text: str,
#         document_id: str,
#         document_title: str
#     ) -> List[dict]:
#         """Split text into overlapping chunks."""
#         chunks = []
#         start = 0
        
#         while start < len(text):
#             end = start + self.chunk_size
#             chunk_text = text[start:end]
            
#             chunks.append({
#                 'text': chunk_text,
#                 'document_id': document_id,
#                 'document_title': document_title,
#                 'chunk_index': len(chunks),
#                 'start_pos': start,
#                 'end_pos': end,
#             })
            
#             start += self.chunk_size - self.chunk_overlap
        
#         return chunks
