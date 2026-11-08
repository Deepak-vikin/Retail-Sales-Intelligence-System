import re


class SQLValidator:

    @staticmethod
    def validate(sql):
        sql = sql.strip()

        if sql.startswith("```"):
            sql = re.sub(r"```sql|```", "", sql, flags=re.IGNORECASE).strip()

        if ";" in sql[:-1]:
            raise ValueError("Multiple SQL statements are not allowed.")

        forbidden = [
            "INSERT", "UPDATE", "DELETE",
            "DROP", "ALTER", "CREATE",
            "TRUNCATE", "GRANT", "REVOKE"
        ]

        upper_sql = sql.upper()

        for keyword in forbidden:
            if re.search(rf"\b{keyword}\b", upper_sql):
                raise ValueError(f"Forbidden SQL operation: {keyword}")

        if not upper_sql.startswith(("SELECT", "WITH")):
            raise ValueError("Only SELECT queries are allowed.")

        return sql