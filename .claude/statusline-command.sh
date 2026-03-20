#!/usr/bin/env bash
input=$(cat)
model=$(echo "$input" | jq -r '.model.display_name // "Claude"')
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // "unknown"')
used=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
if [ -n "$used" ]; then
  used_int=$(printf "%.0f" "$used")
  bar_width=20
  filled=$((used_int * bar_width / 100))
  empty=$((bar_width - filled))
  bar=""
  i=0; while [ $i -lt $filled ]; do bar="${bar}#"; i=$((i+1)); done
  i=0; while [ $i -lt $empty ]; do bar="${bar}-"; i=$((i+1)); done
  if [ "$used_int" -ge 90 ]; then color="\033[31m"; elif [ "$used_int" -ge 70 ]; then color="\033[33m"; else color="\033[32m"; fi
  printf "%s | %s | ctx: ${color}[%s]\033[0m %d%%\n" "$model" "$cwd" "$bar" "$used_int"
else
  printf "%s | %s\n" "$model" "$cwd"
fi
