# rag_processor_minimal.py - МИНИМАЛЬНАЯ ВЕРСИЯ БЕЗ WORD ПОДДЕРЖКИ
import os
import logging
from typing import List, Dict, Optional
import asyncio
import re

logger = logging.getLogger(__name__)

class MinimalRAGProcessor:
    """Минимальная RAG система - работает с текстовыми файлами"""
    
    def __init__(self):
        self.documents = {}  # {doc_name: [chunks]}
        self.is_initialized = True
        
    async def initialize(self):
        logger.info("✅ Минимальная RAG система готова к работе")
        return True
    
    def _chunk_text(self, text: str, chunk_size: int = 500) -> List[str]:
        """Разбивает текст на фрагменты"""
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), chunk_size):
            chunk = ' '.join(words[i:i + chunk_size])
            chunks.append(chunk)
            
        return chunks
    
    async def process_text_document(self, file_path: str) -> bool:
        """Обрабатывает текстовый файл"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                document_text = f.read()
            
            if not document_text.strip():
                logger.warning(f"Документ {file_path} пуст")
                return False
            
            # Разбиваем на фрагменты
            chunks = self._chunk_text(document_text)
            doc_name = os.path.basename(file_path)
            self.documents[doc_name] = chunks
            
            logger.info(f"✅ Документ {doc_name} обработан: {len(chunks)} фрагментов")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки документа {file_path}: {e}")
            return False
    
    async def search_similar(self, query: str, n_results: int = 3) -> List[Dict]:
        """Простой текстовый поиск по ключевым словам"""
        if not self.documents:
            return []
        
        query_words = set(query.lower().split())
        results = []
        
        for doc_name, chunks in self.documents.items():
            for i, chunk in enumerate(chunks):
                chunk_lower = chunk.lower()
                # Простой подсчет совпадающих слов
                score = sum(1 for word in query_words if word in chunk_lower)
                
                if score > 0:
                    results.append({
                        'content': chunk,
                        'source': doc_name,
                        'chunk_id': i,
                        'relevance_score': score
                    })
        
        # Сортируем по релевантности и берем топ-N
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        return results[:n_results]
    
    async def get_relevant_context(self, query: str, max_chars: int = 1500) -> str:
        """Получение релевантного контекста"""
        similar_docs = await self.search_similar(query, n_results=5)
        
        if not similar_docs:
            return ""
        
        context_parts = []
        total_chars = 0
        
        for doc in similar_docs:
            doc_text = f"[Источник: {doc['source']}]\n{doc['content']}\n\n"
            if total_chars + len(doc_text) <= max_chars:
                context_parts.append(doc_text)
                total_chars += len(doc_text)
            else:
                break
        
        return "\n".join(context_parts)
    
    async def get_collection_stats(self) -> Dict:
        """Статистика коллекции"""
        total_chunks = sum(len(chunks) for chunks in self.documents.values())
        return {
            "total_chunks": total_chunks,
            "total_documents": len(self.documents),
            "is_initialized": self.is_initialized,
            "documents": list(self.documents.keys())
        }

# Глобальный экземпляр
rag_processor = MinimalRAGProcessor()