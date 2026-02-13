# test_chromadb.py
try:
    import chromadb
    print("✅ ChromaDB установлен корректно")
except ImportError as e:
    print(f"❌ Ошибка: {e}")