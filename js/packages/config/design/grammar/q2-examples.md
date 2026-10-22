# Q2 examples: must values be separated by a space?

Owner, 2026-10-22: "I need concrete examples to review with points and counterpoints."

How each column was produced:

- **Today:** today's parser, run.
- **A:** the REx test parser for `config.ebnf`, run.
- **B and C:** reasoning, marked *(r)*.

Two plain words can never touch: touching text is one word (`200ms`). The rule only matters
where a word, a quoted string, a list or a slice meet with no space between them.

The options:

- **A:** values must be separated by a space; a slice must touch its word.
- **B:** only slices must touch.
- **C:** a space is allowed before a slice.

| # | Line | Today | A | B *(r)* | C *(r)* |
|---|---|---|---|---|---|
| 1 | `connect hyperhdr_color[144:152];` | accepted | slice | same | same |
| 2 | `node literal pure_white color:srgb [[1, 1, 1]];` | accepted | list | same | same |
| 3 | `connect sine[50:150] dmx[0:100];` | accepted | 2 slices | same | same |
| 4 | `server{ port 8080; }` | accepted | accepted | same | same |
| 5 | `label "a""b";` | 2 strings, silently | error at the 2nd string | 2 strings | = A |
| 6 | `name"x";` | value `"x"`, silently | error | accepted | = A |
| 7 | `path "/etc/rasl"/x.conf;` | 2 values, silently | error at `/x.conf` | 2 values | = A |
| 8 | `connect [a][b];` | 2 lists | error | 2 lists | = A |
| 9 | `connect a[0:3]b;` | engine connects into port `b` | error at `b` | same as today | = A |
| 10 | `connect sine[50:150]dmx[0:100];` | same as row 3 | error at `dmx` | same as row 3 | = A |
| 11 | `connect x a [0:3];` | same as `a[0:3]` | error, but it talks about a list | = A | slice of `a` |
| 12 | `connect x a[ 0:3 ];` | same as `a[0:3]` | error | = A | = A |
| 13 | `connect foo[1];` | engine drops the slice silently | error | = A | = A |
| 14 | `label "str"[0:3];` | string plus loose tokens | error | error | error |

Points and counterpoints:

- **A.**
  - Point: rows 5–10 become errors that point at the spot; it is one rule everywhere, and the
    tools have checked it.
  - Counterpoint: row 11 is natural to write, and its error talks about a list unless the
    parser adds a hint.
- **B.**
  - Point: the fewest new errors.
  - Counterpoint: rows 5–10 stay silent. Row 7 splits a path in two, and row 9 connects into a
    port the user never meant.
- **C.**
  - Point: row 11 works, as indexing does in Python and Rust.
  - Counterpoints:
    - It reverses `rasl-9ze`'s "postfix with no whitespace".
    - `[...]` after a space becomes a list or a slice depending on its contents.
    - It still needs A or B for rows 5–10.

Prior art (from memory, not checked):

- **nginx and TOML** behave like A.
- **Python** joins `"a""b"` into one string, and allows a space before a subscript.
- **Rust** allows a space before an index, and rejects `name"x"`.
- **Shell** joins `"a""b"` into one word.
