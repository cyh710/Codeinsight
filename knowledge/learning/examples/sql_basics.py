"""SQL 样章的内存演示；只用标准库，不写入项目数据库。"""

import sqlite3


def run_demo() -> dict:
    """返回可核对的查询与约束结果，连接关闭后内存数据消失。"""
    with sqlite3.connect(":memory:") as conn:
        conn.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, price REAL NOT NULL);
            INSERT INTO products VALUES (1, '笔记本', 12.0), (2, '钢笔', 35.0);
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL REFERENCES products(id),
                quantity INTEGER NOT NULL CHECK (quantity > 0)
            );
            INSERT INTO orders VALUES (101, 1, 2), (102, 1, 1), (103, 2, 1);
        """)
        filtered = conn.execute(
            "SELECT name, price FROM products WHERE price < 20 ORDER BY id"
        ).fetchall()
        joined = conn.execute("""
            SELECT orders.id, products.name, orders.quantity, products.price * orders.quantity
            FROM orders JOIN products ON products.id = orders.product_id ORDER BY orders.id
        """).fetchall()
        try:
            conn.execute("INSERT INTO orders VALUES (104, 999, 1)")
        except sqlite3.IntegrityError:
            rejected = True
        else:
            rejected = False
        conn.execute("ALTER TABLE products RENAME TO goods")
        renamed = conn.execute("SELECT COUNT(*) FROM goods").fetchone()[0]
    return {
        "filtered": filtered,
        "joined": joined,
        "invalid_foreign_key_rejected": rejected,
        "renamed_rows": renamed,
    }


if __name__ == "__main__":
    for label, value in run_demo().items():
        print(label, value)
