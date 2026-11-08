import pytest
from app.ai.sql_validaator import SQLValidator


def test_select_allowed():
    sql = "SELECT * FROM products;"
    assert SQLValidator.validate(sql) == sql


def test_with_query_allowed():
    sql = "WITH data AS (SELECT * FROM products) SELECT * FROM data;"
    assert SQLValidator.validate(sql) == sql


@pytest.mark.parametrize("sql", [
    "INSERT INTO products VALUES (1, '123', 'Test');",
    "UPDATE products SET product_name = 'Test';",
    "DELETE FROM products;",
    "DROP TABLE products;",
    "ALTER TABLE products ADD COLUMN test TEXT;",
    "CREATE TABLE test (id INT);",
    "TRUNCATE products;",
    "GRANT ALL ON products TO public;",
    "REVOKE ALL ON products FROM public;"
])
def test_write_operations_rejected(sql):
    with pytest.raises(ValueError):
        SQLValidator.validate(sql)


def test_multiple_statements_rejected():
    sql = "SELECT * FROM products; DELETE FROM products;"
    with pytest.raises(ValueError):
        SQLValidator.validate(sql)


def test_non_select_rejected():
    sql = "SHOW TABLES;"
    with pytest.raises(ValueError):
        SQLValidator.validate(sql)