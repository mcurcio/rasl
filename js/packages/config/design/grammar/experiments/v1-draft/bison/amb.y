/* iterative (readable) form of the syntactic grammar, LALR(1) */
%token WORD STRING NEWLINE
%%
document : stmts ;
stmts    : seps stmt_list opt_header ;
stmt_list: /* empty */ | stmt_list stmt ;
stmt     : header seps | header block seps ;
opt_header: /* empty */ | header ;
seps     : /* empty */ | seps sep ;
header   : WORD values ;
values   : /* empty */ | values value ;
value    : WORD | STRING | list ;
list     : '[' nls ']' | '[' nls items ']' ;
items    : value nls | value nls ',' nls | value nls ',' nls items ;
nls      : /* empty */ | nls NEWLINE ;
sep      : ';' | NEWLINE ;
block    : '{' stmts '}' ;
%%
