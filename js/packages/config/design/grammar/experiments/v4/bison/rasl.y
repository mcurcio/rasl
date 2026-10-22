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
rest_grp_8
  : value rest
  ;
rest_opt_9
  : /* empty */
  | rest_grp_8
  ;
rest_grp_10
  : gap rest_opt_9
  ;
rest_opt_11
  : /* empty */
  | rest_grp_10
  ;
rest
  : rest_opt_11
  ;
gap_grp_12
  : SPACE
  | COMMENT
  ;
gap_plus_13
  : gap_grp_12
  | gap_plus_13 gap_grp_12
  ;
gap
  : gap_plus_13
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
bounds_opt_14
  : /* empty */
  | WORD
  ;
bounds
  : WORD COLON bounds_opt_14
  | COLON WORD
  ;
list_opt_15
  : /* empty */
  | listGap
  ;
list_opt_16
  : /* empty */
  | items
  ;
list
  : LBRACK list_opt_15 list_opt_16 RBRACK
  ;
items_opt_17
  : /* empty */
  | listGap
  ;
items_opt_18
  : /* empty */
  | listGap
  ;
items_opt_19
  : /* empty */
  | items
  ;
items_grp_20
  : COMMA items_opt_18 items_opt_19
  ;
items_opt_21
  : /* empty */
  | items_grp_20
  ;
items
  : value items_opt_17 items_opt_21
  ;
listGap_grp_22
  : SPACE
  | COMMENT
  | NEWLINE
  ;
listGap_plus_23
  : listGap_grp_22
  | listGap_plus_23 listGap_grp_22
  ;
listGap
  : listGap_plus_23
  ;
%%
