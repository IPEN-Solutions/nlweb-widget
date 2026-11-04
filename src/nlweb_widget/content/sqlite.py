"""Optional SQLite + sqlite-vec hybrid retrieval provider."""

import asyncio
import json
import sqlite3
import struct
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..errors import (
    OptionalDependencyError,
    ProviderInitializationError,
    RetrievalError,
)
from ..models import ContentDocument
from .retrieval import EmbeddingProvider, embed_query

SQLITE_VEC_VERSION = "0.1.8"


class SQLiteVecRetrievalStore:
    """Local SQLite retrieval using sqlite-vec KNN plus SQLite FTS5 keyword search.

    The store is intentionally isolated behind the existing RetrievalProvider
    contract. SQLite owns metadata/FTS5 persistence while sqlite-vec owns the
    vector index; hybrid ranking uses reciprocal-rank fusion so neither score
    scale leaks into the public provider contract.
    """

    def __init__(
        self,
        path: str,
        embedding_provider: EmbeddingProvider,
        *,
        dimensions: int = 384,
    ) -> None:
        try:
            import sqlite_vec
        except ImportError as exc:
            raise OptionalDependencyError(
                "SQLite vector support requires the 'sqlite' extra (sqlite-vec)"
            ) from exc
        self._sqlite_vec = sqlite_vec
        self._path = str(Path(path))
        self._embedder = embedding_provider
        self._dimensions = dimensions
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        with self._lock:
            if self._connection is not None:
                return
            path = Path(self._path)
            if path != Path(":memory:"):
                path.parent.mkdir(parents=True, exist_ok=True)
            try:
                connection = sqlite3.connect(self._path, check_same_thread=False)
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=WAL")
                connection.enable_load_extension(True)
                self._sqlite_vec.load(connection)
                connection.enable_load_extension(False)
                version = str(connection.execute("SELECT vec_version()").fetchone()[0])
                if version.lstrip("v") != SQLITE_VEC_VERSION:
                    raise ProviderInitializationError(
                        f"sqlite-vec version {version!r} is unsupported; expected {SQLITE_VEC_VERSION}"
                    )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS nlweb_documents (
                        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                        document_id TEXT NOT NULL UNIQUE,
                        url TEXT NOT NULL,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        schema_object TEXT NOT NULL,
                        site TEXT NOT NULL,
                        metadata TEXT NOT NULL
                    )"""
                )
                connection.execute(
                    """CREATE VIRTUAL TABLE IF NOT EXISTS nlweb_documents_fts
                       USING fts5(document_id UNINDEXED, title, content, site UNINDEXED)"""
                )
                connection.execute(
                    f"""CREATE VIRTUAL TABLE IF NOT EXISTS nlweb_document_vectors
                        USING vec0(document_rowid INTEGER PRIMARY KEY, embedding float[{self._dimensions}])"""
                )
                connection.commit()
                self._connection = connection
            except ProviderInitializationError:
                if "connection" in locals():
                    connection.close()
                raise
            except (OSError, sqlite3.Error, ValueError) as exc:
                if "connection" in locals():
                    connection.close()
                raise ProviderInitializationError(
                    f"SQLite vector store initialization failed for {self._path}: {exc}"
                ) from exc

    async def upsert(
        self, documents: Sequence[ContentDocument] | ContentDocument
    ) -> int:
        items = (
            [documents] if isinstance(documents, ContentDocument) else list(documents)
        )
        if not items:
            return 0
        await self.initialize()
        vectors = await self._embedder.embed([document.content for document in items])
        if len(vectors) != len(items):
            raise ValueError(
                "embedding provider returned an incorrect number of vectors"
            )
        await asyncio.to_thread(self._upsert_sync, items, vectors)
        return len(items)

    def _upsert_sync(
        self, documents: list[ContentDocument], vectors: list[list[float]]
    ) -> None:
        with self._lock:
            connection = self._require_connection()
            try:
                for document, vector in zip(documents, vectors, strict=True):
                    _validate_vector(vector, self._dimensions, document.id)
                    existing = connection.execute(
                        "SELECT rowid FROM nlweb_documents WHERE document_id = ?",
                        (document.id,),
                    ).fetchone()
                    if existing:
                        rowid = int(existing[0])
                        connection.execute(
                            "DELETE FROM nlweb_documents_fts WHERE document_id = ?",
                            (document.id,),
                        )
                        connection.execute(
                            "DELETE FROM nlweb_document_vectors WHERE document_rowid = ?",
                            (rowid,),
                        )
                        connection.execute(
                            """UPDATE nlweb_documents SET url=?, title=?, content=?,
                               schema_object=?, site=?, metadata=? WHERE rowid=?""",
                            (
                                str(document.url),
                                document.title,
                                document.content,
                                json.dumps(
                                    document.schema_object,
                                    ensure_ascii=False,
                                    default=str,
                                ),
                                document.site or "default",
                                json.dumps(
                                    document.metadata, ensure_ascii=False, default=str
                                ),
                                rowid,
                            ),
                        )
                    else:
                        cursor = connection.execute(
                            """INSERT INTO nlweb_documents
                               (document_id,url,title,content,schema_object,site,metadata)
                               VALUES (?,?,?,?,?,?,?)""",
                            (
                                document.id,
                                str(document.url),
                                document.title,
                                document.content,
                                json.dumps(
                                    document.schema_object,
                                    ensure_ascii=False,
                                    default=str,
                                ),
                                document.site or "default",
                                json.dumps(
                                    document.metadata, ensure_ascii=False, default=str
                                ),
                            ),
                        )
                        rowid = int(cursor.lastrowid)
                    connection.execute(
                        "INSERT INTO nlweb_documents_fts(document_id,title,content,site) VALUES (?,?,?,?)",
                        (
                            document.id,
                            document.title,
                            document.content,
                            document.site or "default",
                        ),
                    )
                    connection.execute(
                        "INSERT INTO nlweb_document_vectors(document_rowid,embedding) VALUES (?,?)",
                        (rowid, _serialize_f32(vector)),
                    )
                connection.commit()
            except (sqlite3.Error, ValueError) as exc:
                connection.rollback()
                raise RetrievalError(f"SQLite vector upsert failed: {exc}") from exc

    async def delete(self, ids: Sequence[str]) -> int:
        values = list(ids)
        if not values:
            return 0
        await self.initialize()
        return await asyncio.to_thread(self._delete_sync, values)

    def _delete_sync(self, ids: list[str]) -> int:
        with self._lock:
            connection = self._require_connection()
            try:
                rows = connection.execute(
                    f"SELECT rowid, document_id FROM nlweb_documents WHERE document_id IN ({','.join('?' for _ in ids)})",
                    ids,
                ).fetchall()
                for rowid, document_id in rows:
                    connection.execute(
                        "DELETE FROM nlweb_document_vectors WHERE document_rowid = ?",
                        (rowid,),
                    )
                    connection.execute(
                        "DELETE FROM nlweb_documents_fts WHERE document_id = ?",
                        (document_id,),
                    )
                    connection.execute(
                        "DELETE FROM nlweb_documents WHERE rowid = ?", (rowid,)
                    )
                connection.commit()
                return len(rows)
            except sqlite3.Error as exc:
                connection.rollback()
                raise RetrievalError(f"SQLite vector delete failed: {exc}") from exc

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        site: str | None = None,
    ) -> list[tuple[ContentDocument, float]]:
        await self.initialize()
        vector = await embed_query(self._embedder, query)
        _validate_vector(vector, self._dimensions, "query")
        return await asyncio.to_thread(
            self._search_sync, query, vector, max(1, limit), site
        )

    def _search_sync(
        self,
        query: str,
        vector: list[float],
        limit: int,
        site: str | None,
    ) -> list[tuple[ContentDocument, float]]:
        with self._lock:
            connection = self._require_connection()
            try:
                candidates = max(limit * 4, 20)
                vector_sql = (
                    "SELECT document_rowid, distance FROM nlweb_document_vectors "
                    "WHERE embedding MATCH ? ORDER BY distance LIMIT ?"
                )
                vector_rows = connection.execute(
                    vector_sql, (_serialize_f32(vector), candidates)
                ).fetchall()
                vector_rank = {
                    int(row[0]): index + 1 for index, row in enumerate(vector_rows)
                }

                terms = _fts_terms(query)
                fts_rank: dict[str, int] = {}
                if terms:
                    fts_sql = (
                        "SELECT document_id FROM nlweb_documents_fts "
                        "WHERE nlweb_documents_fts MATCH ?"
                    )
                    params: list[Any] = [_fts_query(terms)]
                    if site:
                        fts_sql += " AND site = ?"
                        params.append(site)
                    fts_sql += " ORDER BY bm25(nlweb_documents_fts) LIMIT ?"
                    params.append(candidates)
                    fts_rows = connection.execute(fts_sql, params).fetchall()
                    fts_rank = {
                        str(row[0]): index + 1 for index, row in enumerate(fts_rows)
                    }

                rowids = set(vector_rank)
                if fts_rank:
                    placeholders = ",".join("?" for _ in fts_rank)
                    document_rows = connection.execute(
                        f"SELECT rowid, document_id FROM nlweb_documents WHERE document_id IN ({placeholders})",
                        list(fts_rank),
                    ).fetchall()
                    rowids.update(int(row[0]) for row in document_rows)
                if not rowids:
                    return []

                placeholders = ",".join("?" for _ in rowids)
                params = list(rowids)
                sql = (
                    f"SELECT rowid,document_id,url,title,content,schema_object,site,metadata "
                    f"FROM nlweb_documents WHERE rowid IN ({placeholders})"
                )
                if site:
                    sql += " AND site = ?"
                    params.append(site)
                rows = connection.execute(sql, params).fetchall()
                ranked = []
                for row in rows:
                    rowid = int(row[0])
                    document_id = str(row[1])
                    score = _rrf_score(
                        vector_rank.get(rowid), fts_rank.get(document_id)
                    )
                    ranked.append((_row_to_document(row), score))
                ranked.sort(key=lambda item: item[1], reverse=True)
                return ranked[:limit]
            except sqlite3.Error as exc:
                raise RetrievalError(f"SQLite vector search failed: {exc}") from exc

    async def health(self) -> dict[str, object]:
        await self.initialize()
        return await asyncio.to_thread(self._health_sync)

    def _health_sync(self) -> dict[str, object]:
        with self._lock:
            connection = self._require_connection()
            try:
                version = str(connection.execute("SELECT vec_version()").fetchone()[0])
                count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM nlweb_documents"
                    ).fetchone()[0]
                )
                return {
                    "backend": "sqlite+sqlite-vec",
                    "path": self._path,
                    "dimensions": self._dimensions,
                    "vec_version": version,
                    "documents": count,
                    "status": "ok",
                }
            except sqlite3.Error as exc:
                raise RetrievalError(
                    f"SQLite vector health check failed: {exc}"
                ) from exc

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    def _close_sync(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise ProviderInitializationError("SQLite vector store is not initialized")
        return self._connection


def _serialize_f32(vector: Sequence[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *[float(value) for value in vector])


def _validate_vector(vector: Sequence[float], dimensions: int, context: str) -> None:
    if len(vector) != dimensions:
        raise ValueError(
            f"Vector dimension mismatch for {context}: expected {dimensions}, got {len(vector)}"
        )


def _fts_terms(query: str) -> list[str]:
    return [term for term in query.replace('"', " ").split() if term.strip()]


def _fts_query(terms: list[str]) -> str:
    # Quote each token so punctuation is treated as data rather than FTS syntax.
    return " AND ".join(f'"{term.replace(chr(34), "")}"' for term in terms)


def _rrf_score(vector_rank: int | None, fts_rank: int | None) -> float:
    k = 60.0
    return (1.0 / (k + vector_rank) if vector_rank else 0.0) + (
        1.0 / (k + fts_rank) if fts_rank else 0.0
    )


def _row_to_document(row: Sequence[Any]) -> ContentDocument:
    return ContentDocument(
        id=str(row[1]),
        url=str(row[2]),
        title=str(row[3]),
        content=str(row[4]),
        schema_object=json.loads(row[5]) if row[5] else {},
        site=str(row[6]) if row[6] else None,
        metadata=json.loads(row[7]) if row[7] else {},
    )
