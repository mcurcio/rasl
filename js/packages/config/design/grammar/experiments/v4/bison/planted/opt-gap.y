%token BOM COLON COMMA COMMENT LBRACE LBRACK NEWLINE RBRACE RBRACK SEMI SPACE STRING WORD
%expect 0
%start document
%%
document_opt_1
  : /* empty */
  | BOM
  ;
document
  : document_opt_1 statements
  ;
statements_star_2
  : /* empty */
  | statements_star_2 filler
  ;
statements_star_3
  : /* empty */
  | statements_star_3 filler
  ;
statements_grp_4
  : directive statements_star_3
  ;
statements_star_5
  : /* empty */
  | statements_star_5 statements_grp_4
  ;
statements_opt_6
  : /* empty */
  | lastDirective
  ;
statements
  : statements_star_2 statements_star_5 statements_opt_6
  ;
filler
  : SPACE
  | COMMENT
  | NEWLINE
  | SEMI
  ;
directive_grp_7
  : separator
  | block
  ;
directive
  : header directive_grp_7
  ;
lastDirective
  : header
  ;
header
  : WORD rest
  ;
rest_opt_8
  : /* empty */
  | gap
  ;
rest_grp_9
  : value rest
  ;
rest_opt_10
  : /* empty */
  | rest_grp_9
  ;
rest_grp_11
  : rest_opt_8 rest_opt_10
  ;
rest_opt_12
  : /* empty */
  | rest_grp_11
  ;
rest
  : rest_opt_12
  ;
gap_grp_13
  : SPACE
  | COMMENT
  ;
gap_plus_14
  : gap_grp_13
  | gap_plus_14 gap_grp_13
  ;
gap
  : gap_plus_14
  ;
separator
  : SEMI
  | NEWLINE
  ;
block
  : LBRACE statements RBRACE
  ;
value
  : WORD
  | STRING
  | slicedWord
  | list
  ;
slicedWord
  : WORD LBRACK bounds RBRACK
  ;
bounds_opt_15
  : /* empty */
  | WORD
  ;
bounds
  : WORD COLON bounds_opt_15
  | COLON WORD
  ;
list_opt_16
  : /* empty */
  | listGap
  ;
list_opt_17
  : /* empty */
  | items
  ;
list
  : LBRACK list_opt_16 list_opt_17 RBRACK
  ;
items_opt_18
  : /* empty */
  | listGap
  ;
items_opt_19
  : /* empty */
  | listGap
  ;
items_opt_20
  : /* empty */
  | items
  ;
items_grp_21
  : COMMA items_opt_19 items_opt_20
  ;
items_opt_22
  : /* empty */
  | items_grp_21
  ;
items
  : value items_opt_18 items_opt_22
  ;
listGap_grp_23
  : SPACE
  | COMMENT
  | NEWLINE
  ;
listGap_plus_24
  : listGap_grp_23
  | listGap_plus_24 listGap_grp_23
  ;
listGap
  : listGap_plus_24
  ;
%%
