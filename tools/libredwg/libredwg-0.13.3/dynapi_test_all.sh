#!/bin/sh
srcdir="."
top_builddir="."
# dummy to please shellcheck
test -z "$top_builddir" && echo $top_builddir

if [ -n "$VALGRIND" ] && [ -n "$LOG_COMPILER" ]; then
    TESTPROG="$LOG_COMPILER $LOG_FLAGS"
elif [ -n "" ]; then
    TESTPROG=""
else
    TESTPROG="${top_builddir}/libtool --mode=execute"
fi

for d in "$srcdir"/test/test-data/*.dwg "$srcdir"/test/test-data/*/*.dwg; do
    INPUT="$d" $TESTPROG test/unit-testing/dynapi_test || echo "$d"
done
