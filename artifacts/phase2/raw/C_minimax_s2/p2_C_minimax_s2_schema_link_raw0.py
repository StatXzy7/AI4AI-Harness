"""Harness that first extracts referenced tables/columns from the question, then prompts the frozen solver to write SQL against that linked schema subset."""
from ..harness_base import SQLHarness
from .. import bridge


class P2P2CMinimaxS2SchemaLink(SQLHarness):
    def solve(self, question: str) -> str:
        # --- Step 1: Schema Linking --------------------------------------------
        # Ask the LLM to identify which tables/columns are relevant to the question.
        # We force it to emit a structured inventory so downstream parsing is reliable.
        linker_system = (
            "You are a schema-linking module. Given a natural language question and a "
            "database schema, you output ONLY the minimal subset of tables and columns "
            "needed to answer the question. Format strictly as:\n"
            "TABLES: <comma-separated fully-qualified table names>\n"
            "COLUMNS: <comma-separated fully-qualified column names, one per table allowed>\n"
            "If none apply, output TABLES: NONE and COLUMNS: NONE."
        )
        linker_prompt = (
            f"Schema:\n{self.schema}\n\n"
            f"Question: {question}\n\n"
            "Linked subset:"
        )
        linker_response = self.llm(linker_prompt, system=linker_system, temperature=0.0, n=1)

        tables = []
        columns = []
        for raw_line in linker_response.splitlines():
            line = raw_line.strip()
            if line.upper().startswith("TABLES:"):
                value = line.split(":", 1)[1].strip()
                if value and value.upper() != "NONE":
                    tables = [t.strip() for t in value.split(",") if t.strip()]
            elif line.upper().startswith("COLUMNS:"):
                value = line.split(":", 1)[1].strip()
                if value and value.upper() != "NONE":
                    columns = [c.strip() for c in value.split(",") if c.strip()]

        # Build a reduced-schema string containing only the linked tables/columns.
        # We keep the original CREATE TABLE blocks but drop any table the linker did not pick.
        linked_schema = self._filter_schema(self.schema, tables, columns)
        if not linked_schema.strip():
            # If linking produced nothing usable, fall back to the full schema so the
            # frozen solver still has something to work with.
            linked_schema = self.schema

        # --- Step 2: SQL Generation against the Linked Subset ----------------
        solver_system = (
            "You are a Text-to-SQL generator. Use ONLY the tables and columns explicitly "
            "present in the provided schema subset. Produce a single, executable SQLite "
            "SQL statement that answers the question. Output the SQL and nothing else."
        )
        solver_prompt = (
            f"Linked Schema:\n{linked_schema}\n\n"
            f"Question: {question}\n\n"
            "SQL:"
        )
        solver_response = self.llm(solver_prompt, system=solver_system, temperature=0.0, n=1)

        candidate = bridge.extract_sql(solver_response)

        # --- Step 3: Optional execution check & single retry -----------------
        result = self.execute(candidate)
        if result.get("ok"):
            return candidate

        # Retry once with the error feedback, still scoped to the linked schema.
        retry_prompt = (
            f"Linked Schema:\n{linked_schema}\n\n"
            f"Question: {question}\n\n"
            f"Your previous SQL was:\n{candidate}\n\n"
            f"It produced this error:\n{result.get('error', 'unknown error')}\n\n"
            "Correct the SQL and output only the fixed statement."
        )
        retry_response = self.llm(retry_prompt, system=solver_system, temperature=0.0, n=1)
        final_sql = bridge.extract_sql(retry_response)
        return final_sql

    # ------------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------------
    def _filter_schema(self, full_schema: str, tables, columns):
        """
        Reduce the full CREATE TABLE schema to only the linked tables/columns.

        Strategy: scan for CREATE TABLE blocks, keep a block if its table name is in
        `tables` (case-insensitive). Within a kept block, drop column lines whose
        identifiers are not in `columns` (when columns is non-empty).
        """
        if not tables:
            # No table guidance -> keep the full schema; columns hint alone isn't enough
            # to safely rewrite CREATE statements without risking parse-breaking edits.
            return full_schema

        tables_upper = {t.upper() for t in tables}
        columns_upper = {c.upper().split(".")[-1] for c in columns} if columns else set()

        lines = full_schema.splitlines()
        kept_blocks = []
        current_block = []
        current_table = None
        inside = False

        def flush():
            if not current_block:
                return
            if current_table is None or current_table.upper() not in tables_upper:
                return
            if columns_upper:
                filtered = []
                for ln in current_block:
                    stripped = ln.strip().rstrip(",")
                    if not stripped or stripped.upper().startswith(("CREATE", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT", ")")):
                        filtered.append(ln)
                        continue
                    first_token = stripped.split(None, 1)[0].strip("`,[]\"")
                    if first_token.upper() in columns_upper:
                        filtered.append(ln)
                kept_blocks.extend(filtered)
            else:
                kept_blocks.extend(current_block)

        for line in lines:
            stripped = line.strip()
            if stripped.upper().startswith("CREATE TABLE"):
                # start of a new block
                flush()
                current_block = [line]
                inside = True
                # Extract table name (handle optional IF NOT EXISTS and backticks/quotes)
                rest = stripped[len("CREATE TABLE"):].strip()
                if rest.upper().startswith("IF NOT EXISTS"):
                    rest = rest[len("IF NOT EXISTS"):].strip()
                # take first token, strip punctuation
                name_token = rest.split(None, 1)[0].strip("`,;\"")
                current_table = name_token
                continue
            if inside:
                current_block.append(line)
                if ";" in line:
                    flush()
                    current_block = []
                    current_table = None
                    inside = False

        flush()

        if not kept_blocks:
            return full_schema
        return "\n".join(kept_blocks)