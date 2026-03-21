#!/bin/sh
srcdir="."
top_builddir="."
# dummy to please shellcheck, needed for LTEXEC
test -z "$top_builddir" && echo $top_builddir

if [ -n "$VALGRIND" ] && [ -n "$LOG_COMPILER" ]; then
    TESTPROG="$LOG_COMPILER $LOG_FLAGS"
elif [ -n "" ]; then
    TESTPROG=""
else
    TESTPROG="${top_builddir}/libtool --mode=execute"
fi

cd test/unit-testing || exit
list="$(make -s list)"
# shellcheck disable=SC2086
make -s -j4 $list
cd - || exit

for t in $list; do
    echo "$t"
    # -a for all (no max 6), -n for no coverage checks
    $TESTPROG "test/unit-testing/$t" -an "$srcdir/test/test-data/"
    $TESTPROG "test/unit-testing/$t" -an "$srcdir/test/test-big/"
    $TESTPROG "test/unit-testing/$t" -an "$srcdir/test/test-old/"
done
