#!/bin/sh
cat << EOF |\
pn53x-tamashell |\
awk -f getRx.awk
4a 01 03 00
p 10
44 00 e8 00
EOF
