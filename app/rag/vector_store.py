from app.core.database import connection
from app.rag.embedding_service import EmbeddingService
from psycopg2.extras import Json


embedding_service = EmbeddingService()


def add_document(content, metadata=None):
    embedding = embedding_service.embed(content)

    conn = connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO rag_documents (content, metadata, embedding) VALUES (%s, %s, %s);",
            (content, Json(metadata or {}), embedding)
        )

        conn.commit()

        return {
            "action": "inserted"
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def upsert_document(content, metadata=None):
    metadata = metadata or {}
    embedding = embedding_service.embed(content)

    document_type = metadata.get("type")
    document_date = str(metadata.get("date"))

    conn = connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id FROM rag_documents WHERE metadata->>'type' = %s AND metadata->>'date' = %s LIMIT 1;",
            (document_type, document_date)
        )

        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                "UPDATE rag_documents SET content = %s, metadata = %s, embedding = %s, updated_at = NOW() WHERE id = %s;",
                (
                    content,
                    Json(metadata),
                    embedding,
                    existing[0]
                )
            )

            document_id = existing[0]
            action = "updated"

        else:
            cursor.execute(
                "INSERT INTO rag_documents (content, metadata, embedding) VALUES (%s, %s, %s) RETURNING id;",
                (
                    content,
                    Json(metadata),
                    embedding
                )
            )

            document_id = cursor.fetchone()[0]
            action = "inserted"

        conn.commit()

        return {
            "id": document_id,
            "action": action
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def search_documents(query, limit=5):
    query_embedding = embedding_service.embed(query)

    conn = connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT content, metadata, 1 - (embedding <=> %s::vector) AS similarity FROM rag_documents WHERE embedding IS NOT NULL ORDER BY embedding <=> %s::vector LIMIT %s;",
            (
                query_embedding,
                query_embedding,
                limit
            )
        )

        return cursor.fetchall()

    finally:
        conn.close()