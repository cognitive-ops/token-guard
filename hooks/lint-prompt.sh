#!/usr/bin/env bash
# UserPromptSubmit hook: score the prompt on clarity/specificity/context-efficiency.
# Pushes ONLY scores + counts to Loki as event="prompt_lint" — never prompt text
# (deliberately, to avoid compounding log-prompt.sh's raw-text-storage tradeoff).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/lib.sh"
read_input
prompt="$(hook_field '.prompt')"
session_id="$(hook_field '.session_id')"
[ -z "$prompt" ] && exit 0

# Best-effort dev identity — Claude Code's hook payload carries no user/email
# field, so this is a local git config lookup, not an org-verified identity.
# May not match the email used elsewhere (Keycloak/Anthropic Admin API).
user_email="$(git config --get user.email 2>/dev/null || echo unknown)"

# --- shared pre-computation ---
char_count=${#prompt}
word_count=$(printf '%s' "$prompt" | wc -w)
# Split fenced ``` blocks (pasted code/logs) from prose (the actual instruction).
code_text=$(printf '%s\n' "$prompt" | awk '/^```/{f=!f;next} f{print}')
prose_text=$(printf '%s\n' "$prompt" | awk '/^```/{f=!f;next} !f{print}')
code_chars=${#code_text}
prose_chars=${#prose_text}
[ "$prose_chars" -eq 0 ] && prose_chars=1

# --- clarity: 100, minus penalties for hedging/vagueness, floored at 0 ---
hedge_re='\b(maybe|perhaps|somehow|kind of|sort of|stuff|things|etc\.?|idk|i guess|whatever|not sure)\b'
hedge_hits=$(grep -oiE "$hedge_re" <<<"$prompt" | wc -l)
qmarks=$(grep -o '?' <<<"$prompt" | wc -l)
excess_q=$(( qmarks > 2 ? qmarks - 2 : 0 ))
runon_hits=$(awk -v RS='[.!?]' '{n=split($0,w,/[ \t]+/); if (n>40 && $0 !~ /[,;:\n]/) c++} END{print c+0}' <<<"$prompt")
clarity=$(( 100 - hedge_hits*8 - excess_q*5 - runon_hits*15 ))
(( clarity < 0 )) && clarity=0

# --- specificity: base 20, plus points for concrete anchors, capped at 100 ---
path_hits=$(grep -oE '([A-Za-z0-9_.-]+/){1,}[A-Za-z0-9_.-]+|\b[A-Za-z0-9_-]+\.(ts|tsx|js|jsx|py|go|rb|java|sh|yaml|yml|json|md|sql|css)\b' <<<"$prompt" | wc -l)
quote_hits=$(grep -oE '"[^"]{3,}"|'"'"'[^'"'"']{3,}'"'"'|`[^`]{3,}`' <<<"$prompt" | wc -l)
symbol_hits=$(grep -oE '\b([a-z]+[A-Z][A-Za-z0-9]*|[A-Za-z][a-z0-9]+_[A-Za-z0-9_]+|[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*)\b' <<<"$prompt" | wc -l)
constraint_hits=$(grep -oE "\b(must|should|don't|do not|never|always|only|exactly|requires?)\b" <<<"$prompt" | wc -l)
specificity=$(( 20 + path_hits*12 + quote_hits*10 + symbol_hits*6 + constraint_hits*8 ))
(( specificity > 100 )) && specificity=100

# --- context efficiency: unique-word ratio, minus a paste:prose ratio penalty ---
total_words=$(tr '[:upper:]' '[:lower:]' <<<"$prose_text" | tr -sc '[:alpha:]' '\n' | grep -c .)
unique_words=$(tr '[:upper:]' '[:lower:]' <<<"$prose_text" | tr -sc '[:alpha:]' '\n' | grep . | sort -u | wc -l)
[ "$total_words" -eq 0 ] && total_words=1
context_efficiency=$(awk -v u="$unique_words" -v t="$total_words" -v c="$code_chars" -v p="$prose_chars" 'BEGIN{
  ur=u/t; pr=c/p; excess=(pr>3)?(pr-3):0; pen=excess*10; if(pen>60)pen=60;
  s=100*ur-pen; if(s<0)s=0; if(s>100)s=100; printf "%d", s}')

overall=$(( (clarity + specificity + context_efficiency) / 3 ))

line="$(jq -nc --arg sid "$session_id" --arg email "$user_email" \
  --argjson cc "$char_count" --argjson wc "$word_count" \
  --argjson clarity "$clarity" --argjson specificity "$specificity" \
  --argjson ctx "$context_efficiency" --argjson overall "$overall" \
  '{session_id:$sid, user_email:$email, char_count:$cc, word_count:$wc,
    clarity:$clarity, specificity:$specificity, context_efficiency:$ctx, overall:$overall}')" || exit 0
[ -z "$line" ] && exit 0
push_event "prompt_lint" "$line"
exit 0
