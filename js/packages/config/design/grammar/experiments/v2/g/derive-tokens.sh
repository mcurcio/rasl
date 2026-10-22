#!/bin/sh
# Derive the token-stream grammar from the normative file: every token kind
# (named in the "tokens:" annotation) repeated, then the file's own TOKENS section verbatim.
src="$1"
kinds=$(sed -n "s|^/\* tokens: \(.*\) \*/$|\1|p" "$src")
echo "Tokens ::= ( $(echo $kinds | sed 's/ / | /g') )* EOF"
echo
sed -n '/<?TOKENS?>/,$p' "$src"
