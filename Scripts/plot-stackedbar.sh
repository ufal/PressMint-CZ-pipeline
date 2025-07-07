#!/bin/bash
set -e

INPUT=""
OUTPUT="stacked.png"
METRIC="words"
TEMPFILE=$(mktemp /tmp/gnuplot-stacked.XXXXXX.gnuplot)
TEMP_DATA=$(mktemp /tmp/stats-stacked.XXXXXX.dat)

usage() {
  echo "Usage: $0 -i input.tsv [-o output.png] [-m metric]"
  exit 1
}

while getopts "i:o:m:h" opt; do
  case $opt in
    i) INPUT="$OPTARG" ;;
    o) OUTPUT="$OPTARG" ;;
    m) METRIC="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done

if [ -z "$INPUT" ] || [ ! -f "$INPUT" ]; then
  echo "Invalid input file." >&2
  usage
fi

# Detect column indices
IFS=$'\t' read -r -a headers < <(head -n 1 "$INPUT")
for i in "${!headers[@]}"; do
  case "${headers[$i]}" in
    title) TITLE_IDX=$((i+1)) ;;
    date) DATE_IDX=$((i+1)) ;;
    $METRIC) METRIC_IDX=$((i+1)) ;;
  esac
done

if [ -z "$TITLE_IDX" ] || [ -z "$DATE_IDX" ] || [ -z "$METRIC_IDX" ]; then
  echo "Required columns missing: title, date, $METRIC" >&2
  exit 1
fi

# Prepare intermediate data: first column = year, other columns = titles
#{
#  echo -e "year"
#  tail -n +2 "$INPUT" | cut -f"$DATE_IDX" | sort -u
#} | sort -u > "$TEMP_DATA.years"
seq 1845 1920 > "$TEMP_DATA.years"


cut -f"$TITLE_IDX" "$INPUT" | tail -n +2 | sort -u > "$TEMP_DATA.titles"

# Generate a data matrix: first column = year, other columns = title-wise totals
{
  echo -ne "year"
  while read -r t; do echo -ne "\t$t"; done < "$TEMP_DATA.titles"
  echo

  while read -r y; do
    echo -ne "$y"
    while read -r t; do
      val=$(awk -F'\t' -v y="$y" -v t="$t" -v di=$DATE_IDX -v ti=$TITLE_IDX -v mi=$METRIC_IDX \
        'BEGIN {sum=0} $di==y && $ti==t {sum+=$mi} END {print sum}' "$INPUT")
      echo -ne "\t$val"
    done < "$TEMP_DATA.titles"
    echo
  done < "$TEMP_DATA.years"
} > "$TEMP_DATA"

# Determine output format
ext="${OUTPUT##*.}"
case "$ext" in
  png) term="pngcairo size 1400,800 enhanced font 'Verdana,10'" ;;
  svg) term="svg size 1400,800 dynamic enhanced font 'Verdana,10'" ;;
  pdf) term="pdfcairo size 14cm,10cm enhanced font 'Verdana,10'" ;;
  *) echo "Unsupported format: $ext" >&2; exit 1 ;;
esac

# Create Gnuplot script
num_titles=$(wc -l < "$TEMP_DATA.titles")


cat <<EOF > "$TEMPFILE"
set datafile separator '\t'

set style data histogram
set style histogram rowstacked
set style fill solid noborder
set boxwidth 0.75

set border 3 
set xtics nomirror
set ytics nomirror

set format y "%.0s%c"

set xtics rotate by -65
set key below

set terminal $term
set output '$OUTPUT'

#set title "Stacked $METRIC by year and title"
set ylabel "$METRIC"
set xlabel "Year"
set grid ytics
# X axis is numeric year, default xdata is numeric, no need for set xdata time

set grid xtics

# Define colors for each title (example, adjust count and colors)
set style line 1  lc rgb "#4E79A7"  # muted blue
set style line 2  lc rgb "#F28E2B"  # orange
set style line 3  lc rgb "#59A14F"  # green
set style line 4  lc rgb "#E15759"  # red
set style line 5  lc rgb "#76B7B2"  # teal
set style line 6  lc rgb "#AF7AA1"  # purple
set style line 7  lc rgb "#FF9DA7"  # pink
set style line 8  lc rgb "#9C755F"  # brown
set style line 9  lc rgb "#BAB0AC"  # gray
set style line 10 lc rgb "#D37295"  # rose
set style line 11 lc rgb "#FABFD2"  # light pink
set style line 12 lc rgb "#8CD17D"  # light green
set style line 13 lc rgb "#B6992D"  # gold
set style line 14 lc rgb "#499894"  # blue-green
set style line 15 lc rgb "#D4A6C8"  # lilac
set style line 16 lc rgb "#60B6E3"  # sky blue
set style line 17 lc rgb "#F1CE63"  # yellow
set style line 18 lc rgb "#B07AA1"  # plum
set style line 19 lc rgb "#FFBE7D"  # peach
set style line 20 lc rgb "#A0CBE8"  # soft blue



plot for [i=2:$num_titles+1] '$TEMP_DATA' using i:xtic(1) title columnheader(i) ls i-1
EOF


# Run Gnuplot
gnuplot "$TEMPFILE"

# Clean up
rm -f "$TEMPFILE" "$TEMP_DATA" "$TEMP_DATA.years" "$TEMP_DATA.titles"

echo "Done! Chart saved to $OUTPUT"