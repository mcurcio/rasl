# v1 draft: grammar, soundness, layers (superseded)

> **Status: superseded.** This draft failed review ([v1-review.md](v1-review.md)). It is
> kept as a record of the grammar and the evidence gathered. The review's main finding: the
> recommended tool, Lezer, cannot express this lexical grammar, and Lezer's notation is not EBNF.
> This page condenses the draft's report; experiments are in `experiments/v1-draft/`.

## Conclusions (as drafted)

1. The language can be made provably unambiguous. The grammar built without conflicts in Lezer,
   Lark (strict mode) and Bison, and each tool rejected a deliberately ambiguous variant. All 5
   real `.conf` files in the repo parse.
2. Most of today's lexer quirks have one root cause: a separate Number token that overlaps
   with Word, and brackets that are counted, not parsed.
3. Soundness (a), unambiguity, is proved by tools. Soundness (b), "the parser accepts exactly
   the grammar's language", is tested, not proved: the TS parser is compared against a
   reference parser generated from the grammar.
4. ANTLR4 cannot prove unambiguity: antlr-ng generated a parser from an ambiguous grammar,
   exit 0, with no warning.

## Lexical grammar (W3C EBNF)

```ebnf
/* Longest match; token kinds pairwise disjoint; every character in exactly one token. */
Input          ::= Bom? Token*
Token          ::= Trivia | Newline | Punct | String | Word | ErrorToken
Trivia         ::= Space | LineComment | BlockComment
Space          ::= [#x20#x9]+
LineComment    ::= ( '#' | '//' ) [^#xA#xD]*
BlockComment   ::= '/*' ( [^*] | '*'+ [^*/] )* '*'+ '/'
Newline        ::= #xD? #xA
Punct          ::= ';' | '{' | '}' | '[' | ']' | ','
String         ::= '"' ( [^"\#xA#xD] | Escape )* '"'
                 | "'" ( [^'\#xA#xD] | Escape )* "'"
Escape         ::= '\' [\nrt"']
Word           ::= ( HeadChar WordChar* | '/' ( SlashNext WordChar* )? ) Slice?
Slice          ::= '[' ( Digits ':' Digits? | ':' Digits ) ']'
Digits         ::= [0-9]+
WordChar       ::= Char - ( Delimiter | Control )
HeadChar       ::= WordChar - ( '#' | ':' | '/' )
SlashNext      ::= WordChar - ( '/' | '*' )
Delimiter      ::= [#x20#x9#xA#xD] | [;{}\[\],"']
Control        ::= [#x0-#x1F] | #x7F
ErrorToken     ::= BadSlice | BadEscape | UnterminatedString | UnterminatedComment | StrayChar
```

## Syntactic grammar

```ebnf
Document       ::= Statements
Statements     ::= Separator* ( Directive Separator* )* LastDirective?
Directive      ::= Header ( Separator | Block )
LastDirective  ::= Header
Header         ::= Word Value*
Block          ::= '{' Statements '}'
Separator      ::= ';' | Newline
Value          ::= Word | String | List
List           ::= '[' Newline* ( Value Newline* ( ',' Newline* Value Newline* )* ( ',' Newline* )? )? ']'
```

Value rules (layer 3): `Number ::= '-'? Digits ( '.' Digits )? ( [eE] [+-]? Digits )?`,
`Boolean ::= 'true' | 'false'`. Offsets are UTF-16 code units.

## Where today's code and the old "confirmed" rules disagree

Each "code does" cell was observed by running today's lexer and parser (`probe.ts`, Node 24).

| # | Topic | Code does | Old rule | v1 recommendation |
|---|---|---|---|---|
| 1 | Comments | `//`, `/* */` and `#`; every real file uses `#` | `//` and `/* */` only | Owner question |
| 2 | Word characters | Later characters add `- : @`; `é`, `=`, `$` become error tokens that still turn into arguments | letters, digits, `_`, `.` | Owner question |
| 3 | Numbers | `200ms` gives 2 arguments; `1e` gives 1 with no warning; `0x10` gives `0` and `x10`; `1-2` gives two numbers | not stated | Numbers become words, read by value rules |
| 4 | Slices | `a [0:3]` gives the same tokens as `a[0:3]`; `[x:y]` is the word `x:y` | postfix, no whitespace | Slice inside the Word token (rejected in review: contradicts `rasl-9ze`) |
| 5 | Lists | Brackets are a depth counter; `[1 2]` and `[1;2]` are accepted; an unmatched `]` swallows the following lines | newlines allowed inside | Real list grammar |
| 6 | Escapes | An invalid escape is warning W1004; backslash-newline continues a string | v1 escape set | Both become errors |
| 7 | Offsets | UTF-16 units; `tokens.ts` says "byte offset" | the spec states the unit | UTF-16 |
| 8 | Line endings | A lone CR is whitespace | not stated | CRLF or LF only |
| 9 | Recovery | An error inside a block drops the enclosing directive and its whole block | — | Bug: recover inside the block |
| 10 | Unused codes | E1005, E2002, E2004 and E2005 are never emitted | stable codes | Each code maps to one grammar error |

## Tool results

| Check | Tool | Draft grammar | Planted bad variant |
|---|---|---|---|
| LR conflicts + token overlap | Lezer `@lezer/generator@1` | builds, exit 0 | shift/reduce conflict reported, exit 1 |
| LALR(1) | Lark 1.3.1 strict | OK | Shift/Reduce conflict |
| LALR(1) | Bison 2.3 | no conflicts | 1 shift/reduce, 2 reduce/reduce |
| Token disjointness | interegular | 12 kinds, 0 overlapping | overlap found |
| Ambiguity | antlr-ng 1.0.10 | generates | **also generates, no warning** |
| LL(1) | syntax-cli 0.1.27 | tool bug: wrong FOLLOW sets | — |

Differential run against today's TS parser (`diff.ts`): 0 round-trip failures in 421 inputs.

Tool traps found:

- Lark's strict mode silently skips its collision check for tokens defined with lookahead.
- Lark's lexer takes the first match, not the longest.
- syntax-cli's LL(1) FOLLOW sets are wrong.

## Questions v1 proposed

- Q1: what a bare word may contain, and whether numbers are words.
- Q2: which comment syntaxes to allow.
- Q3: which tool owns the grammar file. v1 recommended Lezer and dropping ANTLR; the review
  found that this gives up the EBNF the owner asked for.

## NOT RUN / NOT VERIFIED (as reported)

- **NOT RUN:**
  - the package's vitest suite (no node_modules in the worktree)
  - Bison 3.8 counterexamples
  - REx
  - Grammarinator
- **NOT VERIFIED:**
  - that the lexer is total (accepts every input)
  - BOM handling
  - that Lezer's `@precedence` is equivalent to longest match. The review then disproved this.
