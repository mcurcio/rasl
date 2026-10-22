"""Wrap the mechanically translated grammar in a C driver: tokens arrive one
kind name per line on stdin, a blank line ends one input. Prints ACCEPT or
REJECT <index of offending token> per input."""
import sys, re
y = open(sys.argv[1]).read()
toks = re.search(r'^%token (.*)$', y, re.M).group(1).split()
table = ',\n'.join(f'  {{"{t}", {t}}}' for t in toks)
pro = '''%{
#include <stdio.h>
#include <string.h>
int yylex(void); void yyerror(const char *s); static int pos, errpos, eoi;
%}
'''
epi = '''
static struct { const char *n; int c; } TAB[] = {
%s
};
int yylex(void) {
  char line[64];
  if (eoi) return 0;
  if (!fgets(line, sizeof line, stdin) || line[0] == '\\n') { eoi = 1; return 0; }
  line[strcspn(line, "\\n")] = 0; pos++;
  for (unsigned i = 0; i < sizeof TAB / sizeof TAB[0]; i++) if (!strcmp(TAB[i].n, line)) return TAB[i].c;
  return 999; /* error token: in no grammar rule */
}
void yyerror(const char *s) { (void)s; errpos = pos - 1; }
int main(void) {
  int c;
  while ((c = getc(stdin)) != EOF) {
    ungetc(c, stdin); pos = 0; eoi = 0; errpos = -1;
    if (yyparse() == 0) puts("ACCEPT"); else printf("REJECT %%d\\n", errpos);
    while (!eoi && yylex() != 0) {}
  }
  return 0;
}
''' % table
y = y.replace('%token', pro + '%token', 1).rstrip()
assert y.endswith('%%')
print(y + epi)
