// @rasl/config grammar ported from config.ebnf (draft 2, '#' comments only).
// Whitespace is explicit: every token is on the default channel, nothing is skipped.
grammar Rasl;

document      : BOM? statements EOF ;
statements    : filler* (directive filler*)* lastDirective? ;
filler        : SPACE | COMMENT | NEWLINE | ';' ;
directive     : header (separator | block) ;
lastDirective : header ;
header        : WORD rest ;
rest          : (gap (value rest)?)? ;
gap           : (SPACE | COMMENT)+ ;
separator     : ';' | NEWLINE ;
block         : '{' statements '}' ;
value         : WORD | STRING | slicedWord | list ;
slicedWord    : WORD '[' bounds ']' ;
bounds        : WORD ':' WORD? | ':' WORD ;
list          : '[' listGap? items? ']' ;
items         : value listGap? (',' listGap? items?)? ;
listGap       : (SPACE | COMMENT | NEWLINE)+ ;

BOM     : '﻿' ;
SPACE   : [ \t]+ ;
NEWLINE : '\n' | '\r\n' ;
COMMENT : '#' CHAR* ;
WORD    : [A-Za-z_./@] [A-Za-z0-9_./@#+:-]* | [0-9-] [A-Za-z0-9_./@#+-]* ;
STRING  : '"' (~["\\\u0000-\u0008\n-\u001F\u007F] | '\\' CHAR)* '"'
        | '\'' (~['\\\u0000-\u0008\n-\u001F\u007F] | '\\' CHAR)* '\'' ;
LBRACE : '{' ; RBRACE : '}' ; LBRACK : '[' ; RBRACK : ']' ; SEMI : ';' ; COMMA : ',' ; COLON : ':' ;
// error tokens: never used by the syntax
UNTERMINATED_STRING : '"' (~["\\\u0000-\u0008\n-\u001F\u007F] | '\\' CHAR)* '\\'?
                    | '\'' (~['\\\u0000-\u0008\n-\u001F\u007F] | '\\' CHAR)* '\\'? ;
BAD_CHAR : . ;
fragment CHAR : [\t -~\u0080-퟿-\u{10FFFF}] ;
