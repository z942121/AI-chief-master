"""菜谱知识库入库脚本。

用法：
    python -m app.rag.ingest           # 增量入库（按文件名去重）
    python -m app.rag.ingest --reset   # 清空后重新入库

将 backend/data/recipes/ 下的 Markdown 文件
向量化后存入 Chroma 向量库（backend/data/chroma/）。

每份完整菜谱 = 一个 Chroma Document，不按标题切分。
"""
import os
import sys
import logging
import glob
import shutil

from dotenv import load_dotenv
from langchain_core.documents import Document

# 确保导入路径正确
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.rag.embedding import get_embedding_function

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 加载 .env
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
load_dotenv(_env_path)

RECIPES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "recipes"
)
CHROMA_PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "chroma"
)
COLLECTION_NAME = "recipe_knowledge_base"


def load_recipes_from_dir(directory: str) -> list[Document]:
    """从目录加载所有 Markdown 菜谱文件，每份菜谱 = 一个完整 Document。"""
    md_files = glob.glob(os.path.join(directory, "*.md"))
    logger.info(f"找到 {len(md_files)} 个菜谱 Markdown 文件")

    documents = []
    for filepath in sorted(md_files):
        filename = os.path.basename(filepath)
        title = os.path.splitext(filename)[0]

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        doc = Document(
            page_content=content,
            metadata={
                "title": title,
                "source": filename,
                "category": "recipe",
            },
        )
        documents.append(doc)
        logger.info(f"  加载: {filename} ({len(content)} 字符)")

    return documents


def reset_vector_store():
    """删除 Chroma 持久化目录，清空所有向量数据。"""
    if os.path.exists(CHROMA_PERSIST_DIR):
        shutil.rmtree(CHROMA_PERSIST_DIR)
        logger.info(f"已清空向量库目录: {CHROMA_PERSIST_DIR}")


def ingest(reset: bool = False):
    """执行入库操作。

    Args:
        reset: True 时先清空向量库再重新入库
    """
    from langchain_chroma import Chroma

    # 1. 加载文档（每份菜谱 = 一个完整 Document，不切分）
    documents = load_recipes_from_dir(RECIPES_DIR)
    if not documents:
        logger.error(f"目录 {RECIPES_DIR} 中没有找到 Markdown 文件")
        return

    logger.info(f"共加载 {len(documents)} 份完整菜谱（不切分）")

    # 2. 如需重置，先清空
    if reset:
        reset_vector_store()

    # 3. 初始化 Chroma
    os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
    embeddings = get_embedding_function()

    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_PERSIST_DIR,
    )

    # 4. 检查已有数据，去重（按 source 文件名）
    collection = vector_store._collection
    existing_count = collection.count()
    logger.info(f"向量库现有 {existing_count} 条记录")

    if existing_count > 0 and not reset:
        try:
            existing = collection.get(include=["metadatas"])
            existing_sources = set()
            for meta in existing["metadatas"]:
                if meta and "source" in meta:
                    existing_sources.add(meta["source"])
            logger.info(f"已有 {len(existing_sources)} 个不同的源文件")
        except Exception as e:
            logger.warning(f"获取已有元数据失败: {e}")
            existing_sources = set()
    else:
        existing_sources = set()

    # 5. 过滤掉已存在的文档
    new_docs = [
        d for d in documents
        if d.metadata.get("source", "") not in existing_sources
    ]

    if not new_docs:
        logger.info("没有新文档需要添加，入库完成。")
        logger.info(f"当前总记录数: {collection.count()}")
        return

    logger.info(f"需要新增 {len(new_docs)} 份完整菜谱")

    # 6. 逐份添加（每份菜谱完整入库，不拆分）
    for i, doc in enumerate(new_docs):
        logger.info(f"  入库 [{i + 1}/{len(new_docs)}]: {doc.metadata['title']}")
        vector_store.add_documents([doc])

    logger.info(f"✅ 入库完成！共新增 {len(new_docs)} 份菜谱")
    logger.info(f"向量库位置: {CHROMA_PERSIST_DIR}")
    logger.info(f"当前总记录数: {collection.count()}")


if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    ingest(reset=reset_flag)
