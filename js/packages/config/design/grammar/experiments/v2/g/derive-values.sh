#!/bin/sh
# Derive a checker grammar for the value rules named in the "values:" annotation.
src="$1"
kinds=$(sed -n "s|^/\* values: \(.*\) \*/\$|\1|p" "$src")
printf 'Check ::='; sep=' '
for k in $kinds; do printf "%s'%s' %s EOF" "$sep" "$k" "$k"; sep=' | '; done; echo
echo
sed -n '/<?TOKENS?>/,$p' "$src"
