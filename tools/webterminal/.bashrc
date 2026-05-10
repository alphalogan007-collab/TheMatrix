# ─────────────────────────────────────────────────────────
#  MindAI Web Terminal  ·  http://localhost:7681
# ─────────────────────────────────────────────────────────
export TERM=xterm-256color
export HISTSIZE=2000
export HISTFILESIZE=2000
export EDITOR=vim

# Coloured prompt: mindai:/workspace$
export PS1='\[\e[1;36m\]mindai\[\e[0m\]:\[\e[1;34m\]\w\[\e[0m\]\$ '

# ── Docker helpers ────────────────────────────────────────
COMPOSE_FILE="/infra/docker-compose.topology.yml"

alias dc="docker compose -f $COMPOSE_FILE"
alias up="docker compose -f $COMPOSE_FILE up -d"
alias down="docker compose -f $COMPOSE_FILE down"
alias rebuild="docker compose -f $COMPOSE_FILE up --build -d"
alias ps="docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

# Logs
alias logs-all="docker compose -f $COMPOSE_FILE logs -f --tail=50"
alias logs-seed="docker logs mindai_seed -f"
alias logs-backend="docker logs mindai_backend -f"
alias logs-guidance="docker logs mindai_guidance -f"
alias logs-redis="docker logs mindai_redis -f"

logs() {
  # Usage: logs <layer_num_or_name>   e.g. logs 3  or  logs seed
  docker logs "mindai_${1}" -f
}

# ── Redis helpers ─────────────────────────────────────────
RC="redis-cli -u ${REDIS_URL:-redis://:changeme_redis_dev@redis:6379/0}"

alias rc="$RC"
alias redis-ping="$RC ping"
alias redis-streams="$RC xlen seed:input ; for i in 1 2 3 4 5 6 7; do echo -n \"space:layer\$i → \"; $RC xlen space:layer\$i; done"
alias redis-events="$RC xrevrange spirit:events + - COUNT 5"
alias corpus="$RC hkeys guidance:corpus"
alias corpus-count="$RC hlen guidance:corpus"

# Last N guidance events
guidance-events() {
  $RC xrevrange guidance:events + - COUNT "${1:-10}"
}

# Dump content of one guidance file by file_id
guidance-get() {
  $RC hget guidance:corpus "$1" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('content','')[:3000])"
}

# Push a test message into the seed stream
seed-test() {
  local msg="${1:-Hello MindAI}"
  $RC xadd seed:input '*' \
    input_type text \
    content "$msg" \
    source webterminal \
    session_id "wt-$(date +%s)"
  echo "→ pushed to seed:input"
}

# ── Guidance inbox ────────────────────────────────────────
alias inbox="ls -lh /guidance/inbox/"
alias inbox-drop="cp"         # e.g.  inbox-drop myfile.pdf /guidance/inbox/

# ── Misc ──────────────────────────────────────────────────
alias ll="ls -lah --color=auto"
alias curl-json='curl -s -H "Content-Type: application/json"'

# Health check shortcut
health() {
  curl -s http://backend:8000/health | python3 -m json.tool
}

# ── Welcome banner ────────────────────────────────────────
mindai_help() {
cat << 'EOF'

  ╔══════════════════════════════════════════════════╗
  ║         MindAI Web Terminal — Quick Ref          ║
  ╠══════════════════════════════════════════════════╣
  ║  CONTAINERS                                      ║
  ║   ps                  list running containers    ║
  ║   logs-seed           seed container logs        ║
  ║   logs-guidance       guidance scanner logs      ║
  ║   logs-all            all containers             ║
  ║   logs <name>         e.g. logs layer3           ║
  ║   rebuild             docker compose up --build  ║
  ║                                                  ║
  ║  REDIS                                           ║
  ║   redis-ping          test connectivity          ║
  ║   redis-streams       stream lengths             ║
  ║   redis-events        last 5 spirit:events       ║
  ║   seed-test [msg]     push msg to seed:input     ║
  ║                                                  ║
  ║  GUIDANCE                                        ║
  ║   inbox               list guidance/inbox/       ║
  ║   corpus              list consumed file IDs     ║
  ║   corpus-count        total files in Redis       ║
  ║   guidance-events [n] last N ingest events       ║
  ║   guidance-get <id>   preview file content       ║
  ║                                                  ║
  ║  BACKEND                                         ║
  ║   health              GET /health                ║
  ╚══════════════════════════════════════════════════╝

  Type  mindai_help  any time to see this again.

EOF
}

mindai_help
