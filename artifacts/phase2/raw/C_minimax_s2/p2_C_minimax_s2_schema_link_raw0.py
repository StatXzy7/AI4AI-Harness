"""Schema-linking harness: identifies tables/columns referenced in the question, restricts the schema to that subset, then asks the frozen solver to generate SQL."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2SchemaLink(SQLHarness):
    # Candidate table names to probe for in the schema.
    _TABLE_HINTS = [
        "customers", "customer", "orders", "order_items", "items",
        "products", "product", "categories", "category", "suppliers",
        "supplier", "employees", "employee", "shippers", "shipper",
        "regions", "region", "territories", "territory",
        "invoices", "invoice", "payments", "payment",
        "students", "student", "courses", "course", "enrollments",
        "enrollment", "departments", "department", "teachers", "teacher",
        "books", "book", "authors", "author", "publishers", "publisher",
        "movies", "movie", "actors", "actor", "directors", "director",
        "songs", "song", "albums", "album", "artists", "artist",
        "matches", "match", "players", "player", "teams", "team",
        "tickets", "ticket", "flights", "flight", "airports", "airport",
        "airlines", "airline", "reservations", "reservation",
        "users", "user", "posts", "post", "comments", "comment",
        "transactions", "transaction", "accounts", "account",
        "countries", "country", "cities", "city", "addresses", "address",
        "sales", "sale", "purchases", "purchase", "inventory",
    ]

    # Candidate column names (lowercased) to probe against.
    _COLUMN_HINTS = [
        "customer_id", "customer_name", "customer_email", "customer_phone",
        "order_id", "order_date", "order_total", "order_status",
        "product_id", "product_name", "product_price", "category_id",
        "supplier_id", "employee_id", "manager_id", "region_id",
        "territory_id", "shipper_id", "country", "city", "state", "postal_code",
        "phone", "fax", "email", "address", "birth_date", "hire_date",
        "unit_price", "quantity", "discount", "freight", "shipped_date",
        "required_date", "payment_date", "amount", "balance", "credit_limit",
        "student_id", "course_id", "grade", "enrollment_date", "gpa",
        "department_id", "teacher_id", "book_id", "author_id", "publisher_id",
        "isbn", "title", "publication_date", "pages", "genre",
        "movie_id", "actor_id", "director_id", "release_date", "rating",
        "song_id", "album_id", "artist_id", "duration", "genre_id",
        "match_id", "player_id", "team_id", "score", "match_date", "venue",
        "ticket_id", "flight_id", "airport_id", "airline_id", "seat",
        "reservation_id", "departure_date", "arrival_date", "origin", "dest",
        "user_id", "username", "password", "post_id", "comment_id",
        "transaction_id", "account_id", "created_at", "updated_at",
        "first_name", "last_name", "middle_name", "full_name", "name",
        "id", "code", "description", "notes", "status", "type",
    ]

    def _extract_keywords(self, question: str) -> str:
        """Return a deduplicated, schema-friendly keyword list from the question."""
        import re
        text = question.lower()
        # Pull tokens like 'customer id', 'first name', 'order date'
        multi = [
            "customer id", "order id", "product id", "category id",
            "supplier id", "employee id", "region id", "territory id",
            "shipper id", "student id", "course id", "department id",
            "teacher id", "book id", "author id", "publisher id",
            "movie id", "actor id", "director id", "song id", "album id",
            "artist id", "match id", "player id", "team id", "ticket id",
            "flight id", "airport id", "airline id", "reservation id",
            "user id", "post id", "comment id", "transaction id", "account id",
            "first name", "last name", "middle name", "full name",
            "order date", "hire date", "birth date", "shipped date",
            "required date", "payment date", "enrollment date",
            "publication date", "release date", "match date",
            "departure date", "arrival date", "order total",
            "unit price", "product price", "credit limit",
            "customer name", "product name", "company name", "category name",
            "region name", "territory name", "shipper name", "country name",
            "customer email", "customer phone", "postal code",
            "order status",
        ]
        found = set()
        for phrase in multi:
            if phrase in text:
                found.add(phrase)

        # Word tokens (strip punctuation, keep length >= 3)
        tokens = re.findall(r"[a-z_][a-z_]{2,}", text)
        stop = {
            "the", "and", "for", "with", "from", "where", "what", "which",
            "show", "list", "all", "any", "each", "many", "much", "how",
            "are", "was", "were", "did", "does", "can", "could", "would",
            "should", "will", "than", "then", "that", "this", "those",
            "these", "have", "has", "had", "their", "there", "here",
            "give", "find", "tell", "me", "you", "his", "her", "its",
            "our", "your", "but", "not", "also", "into", "over", "under",
            "between", "after", "before", "above", "below", "about",
            "select", "sql", "query", "table", "column", "row", "rows",
        }
        for tok in tokens:
            if tok in stop:
                continue
            if len(tok) >= 4:
                found.add(tok)
        return " ".join(sorted(found))

    def _link_schema(self, question: str) -> str:
        """Filter self.schema down to tables/columns whose names appear in the question."""
        schema = self.schema or ""
        if not schema.strip():
            return schema

        q = " " + question.lower() + " "
        ql = q.lower()

        # Identify candidate tables: lines starting with CREATE TABLE / TABLE / `name`.
        import re
        # Try several patterns to segment the schema into table blocks.
        # Pattern 1: CREATE TABLE [name] ( ... );
        pattern_create = re.compile(
            r"(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?)([A-Za-z_][\w]*)([`\"\]]?\s*\([^;]*?\)\s*(?:ENGINE[^;]*|;))",
            re.IGNORECASE | re.DOTALL,
        )
        # Pattern 2: TABLE `name` ( ... );
        pattern_table = re.compile(
            r"(TABLE\s+[`\"\[]?)([A-Za-z_][\w]*)([`\"\]]?\s*\([^;]*?\)\s*;)",
            re.IGNORECASE | re.DOTALL,
        )

        tables = {}  # name -> full block text
        spans = []   # (start, end) of matched blocks so we keep them

        for pat in (pattern_create, pattern_table):
            for m in pat.finditer(schema):
                name = m.group(2)
                start, end = m.span()
                # Avoid duplicating overlaps: keep the longest first.
                if any(s <= start < e for s, e in spans):
                    continue
                tables[name.lower()] = (name, m.group(0))
                spans.append(m.span())

        if not tables:
            # Fallback: line-based segmentation.
            return self._link_schema_linewise(schema, question)

        keywords = self._extract_keywords(question)

        def _name_in_q(name: str) -> bool:
            n = name.lower().strip("`\"[]")
            if not n:
                return False
            if n in ql:
                return True
            # Singular / plural basic variants.
            if n.endswith("ies") and n[:-3] + "y" in ql:
                return True
            if n.endswith("es") and n[:-2] in ql:
                return True
            if n.endswith("s") and n[:-1] in ql:
                return True
            # Underscore vs space.
            spaced = n.replace("_", " ")
            if spaced in ql:
                return True
            return False

        kept = []
        for key, (orig_name, block) in tables.items():
            if _name_in_q(orig_name):
                kept.append(block)
                continue
            # Probe column hints within the table block.
            block_lower = block.lower()
            for col in self._COLUMN_HINTS:
                if col in block_lower and (col in ql or col.replace("_", " ") in ql):
                    kept.append(block)
                    break

        if not kept:
            # Nothing matched: return the original schema to avoid empty context.
            return schema

        header = (
            "-- Schema link: the following tables/columns were matched to the question.\n"
        )
        return header + "\n\n".join(kept)

    def _link_schema_linewise(self, schema: str, question: str) -> str:
        """Fallback linker that retains lines mentioning candidate names."""
        ql = " " + question.lower() + " "
        kept_lines = []
        for line in schema.splitlines():
            low = line.lower()
            for hint in self._TABLE_HINTS + self._COLUMN_HINTS:
                if hint in low:
                    kept_lines.append(line)
                    break
        if not kept_lines:
            return schema
        return "-- Schema link (linewise fallback).\n" + "\n".join(kept_lines)

    def solve(self, question: str) -> str:
        # Step 1: schema-link -- restrict schema to tables/columns mentioned in the question.
        linked_schema = self._link_schema(question)

        # Step 2: build a prompt that supplies only the linked subset.
        system = (
            "You are a precise Text-to-SQL generator. Use ONLY the tables and "
            "columns provided in the schema below. Do not invent columns. "
            "Return a single SQL statement and nothing else."
        )
        prompt = (
            f"Schema (linked subset):\n{linked_schema}\n\n"
            f"Question: {question}\n\n"
            "Write the SQL:"
        )

        # Step 3: ask the frozen weak solver.
        raw = self.llm(prompt, system=system, temperature=0.0, n=1)

        # Step 4: extract the SQL.
        sql = bridge.extract_sql(raw) if raw else ""

        # Step 5: validate by executing; if it fails, retry with a corrective hint.
        if sql:
            res = self.execute(sql)
            if res and res.get("ok"):
                return sql
            err = (res or {}).get("error", "") if res else "unknown error"

            retry_prompt = (
                f"Schema (linked subset):\n{linked_schema}\n\n"
                f"Question: {question}\n\n"
                f"Your previous SQL:\n{sql}\n\n"
                f"It failed with: {err}\n\n"
                "Fix the SQL. Return only the corrected SQL:"
            )
            raw2 = self.llm(retry_prompt, system=system, temperature=0.0, n=1)
            sql2 = bridge.extract_sql(raw2) if raw2 else ""
            if sql2:
                res2 = self.execute(sql2)
                if res2 and res2.get("ok"):
                    return sql2
                # Return the best-effort second attempt rather than the broken first.
                return sql2
            return sql

        # No SQL extracted at all: one fallback pass with a stricter instruction.
        fallback_prompt = (
            f"Schema (linked subset):\n{linked_schema}\n\n"
            f"Question: {question}\n\n"
            "Return ONLY the SQL statement, no prose:"
        )
        raw3 = self.llm(fallback_prompt, system=system, temperature=0.0, n=1)
        sql3 = bridge.extract_sql(raw3) if raw3 else ""
        return sql3 or ""