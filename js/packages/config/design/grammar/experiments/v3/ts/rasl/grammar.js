/**
 * @file @rasl/config grammar, ported from config.ebnf (draft 2, '#' comments only).
 * No implicit whitespace (extras: []), no conflicts:, no prec: every byte is a token.
 */
const CHAR = /[^\x00-\x08\x0A-\x1F\x7F]/; // Char: tab, printable, non-ASCII (surrogates NOT VERIFIED)
module.exports = grammar({
  name: 'rasl',
  extras: $ => [],
  rules: {
    // Document ::= Bom? Statements EOF   (only the start rule may match empty)
    // a leading BOM is stripped by the tree-sitter runtime itself; the adapter keeps it as a token
    document: $ => optional($._statements),
    // Statements ::= Filler* ( Directive Filler* )* LastDirective?   ==  (Filler | Directive)* LastDirective?
    _statements: $ => choice(
      seq(repeat1(choice($._filler, $.directive)), optional(alias($.last_directive, $.directive))),
      alias($.last_directive, $.directive),
    ),
    _filler: $ => choice($.space, $.comment, $.newline, ';'),
    directive: $ => seq($._header, choice(';', $.newline, $.block)),
    last_directive: $ => $._header,
    // Header ::= Word Rest ;  Rest ::= ( Gap ( Value Rest )? )?   ==  Word (Gap Value)* Gap?
    _header: $ => seq($.word, repeat(seq($._gap, $._value)), optional($._gap)),
    _gap: $ => repeat1(choice($.space, $.comment)),
    block: $ => seq('{', optional($._statements), '}'),
    _value: $ => choice($.word, $.string, $.slice, $.list),
    slice: $ => seq($.word, '[', choice(seq($.word, ':', optional($.word)), seq(':', $.word)), ']'),
    list: $ => seq('[', optional($._list_gap), optional($._items), ']'),
    _items: $ => seq($._value, optional($._list_gap), optional(seq(',', optional($._list_gap), optional($._items)))),
    _list_gap: $ => repeat1(choice($.space, $.comment, $.newline)),

    // tokens
    space: $ => /[ \t]+/,
    newline: $ => choice('\n', '\r\n'),
    comment: $ => token(seq('#', repeat(CHAR))),
    word: $ => token(choice(
      seq(/[A-Za-z_.\/@]/, repeat(/[A-Za-z0-9_.\/@#+:\-]/)),
      seq(/[0-9\-]/, repeat(/[A-Za-z0-9_.\/@#+\-]/)),
    )),
    string: $ => token(choice(
      seq('"', repeat(choice(/[^"\\\x00-\x08\x0A-\x1F\x7F]/, seq('\\', CHAR))), '"'),
      seq("'", repeat(choice(/[^'\\\x00-\x08\x0A-\x1F\x7F]/, seq('\\', CHAR))), "'"),
    )),
  },
});
