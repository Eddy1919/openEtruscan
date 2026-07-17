#!/usr/bin/env bash
# Pod session launcher. Creates/removes the per-session worktree and branch
# required by AGENTS.md and prints the kickoff prompt. The charter, pod map,
# and the prompts themselves live in .agents/PODS.md — this script only
# extracts them, so edit prompts there, not here.
#
# usage:
#   pod.sh start <a|b|c|d> <slug>   new pod session (worktree + branch + prompt)
#   pod.sh review <branch>          detached reviewer worktree on a pod branch
#   pod.sh done <worktree-path>     remove a finished session worktree
#   pod.sh status                   list session worktrees and pod branches
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
WT_DIR="$ROOT/.claude/worktrees"
# PODS.md lives in the backend repo; from the frontend repo it is a sibling.
PODS_MD="$ROOT/.agents/PODS.md"
[[ -f "$PODS_MD" ]] || PODS_MD="$ROOT/../openEtruscan/.agents/PODS.md"
[[ -f "$PODS_MD" ]] || { echo "error: cannot find .agents/PODS.md" >&2; exit 1; }

extract_prompt() { # $1 = exact heading text of the prompt's section in PODS.md
  awk -v h="$1" '
    $0 ~ "^#+ " h { in_section = 1; next }
    in_section && /^> ?/ { sub(/^> ?/, ""); print; seen = 1; next }
    in_section && seen { exit }
  ' "$PODS_MD"
}

emit_prompt() {
  printf -- '\n--- kickoff prompt ---\n%s\n----------------------\n' "$1"
  if command -v pbcopy >/dev/null; then
    printf '%s' "$1" | pbcopy
    echo "(copied to clipboard)"
  fi
}

cmd="${1:-}"
case "$cmd" in
  start)
    pod="${2:?usage: pod.sh start <a|b|c|d> <slug>}"
    slug="${3:?usage: pod.sh start <a|b|c|d> <slug>}"
    [[ "$pod" =~ ^[abcd]$ ]] || { echo "error: pod must be a, b, c, or d" >&2; exit 1; }
    git fetch --quiet origin 2>/dev/null || true
    last=$(git for-each-ref --format='%(refname:short)' \
             "refs/heads/pod$pod/*" "refs/remotes/origin/pod$pod/*" |
           sed -E 's|.*/s([0-9]+)-.*|\1|' | sort -n | tail -1)
    n=$(( ${last:-0} + 1 ))
    branch="pod$pod/s$n-$slug"
    wt="$WT_DIR/pod$pod-s$n-$slug"
    git worktree add "$wt" -b "$branch"
    prompt="$(extract_prompt 'Kickoff prompt' | sed "s/<X>/$(printf '%s' "$pod" | tr '[:lower:]' '[:upper:]')/g")"
    printf '\nworktree: %s\nbranch:   %s\nnext:     cd %s   # then launch the pod CLI\n' "$wt" "$branch" "$wt"
    emit_prompt "$prompt"
    ;;
  review)
    branch="${2:?usage: pod.sh review <branch>}"
    git fetch --quiet origin 2>/dev/null || true
    wt="$WT_DIR/review-${branch//\//-}"
    git worktree add --detach "$wt" "$branch"
    prompt="$(extract_prompt 'Cross-model review prompt' | sed "s|<branch>|$branch|g")"
    printf '\nworktree: %s\nnext:     cd %s   # then launch the reviewer CLI\n' "$wt" "$wt"
    emit_prompt "$prompt"
    ;;
  done)
    wt="${2:?usage: pod.sh done <worktree-path>}"
    git worktree remove "$wt"
    echo "removed $wt (branch kept for the merge gate)"
    ;;
  status)
    git worktree list
    echo
    git branch -a --list '*pod[abcd]/*' || true
    ;;
  *)
    sed -n '6,11p' "$0"
    exit 1
    ;;
esac
