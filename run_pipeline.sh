#!/usr/bin/env bash
# security-audit-skill を Claude Code 経由で実リポジトリに対して実行し、
# findings.json を自動生成 -> translate_findings_llm.py で日本語レポート化するまでの
# 一連の流れをつなぐパイプラインスクリプト。
#
# 前提:
#   - Node.js / npx が使えること（security-audit-skill のインストールに使用）
#   - claude CLI (Claude Code) がインストール・認証済みであること
#     https://docs.claude.com/en/docs/claude-code
#   - ANTHROPIC_API_KEY が設定されていること（translate_findings_llm.py 用）
#
# 注意:
#   claude -p での監査実行は、入れ子で別のClaude Codeセッションを起動する形になります。
#   Claude Code on the web / cloud のセッション内から本スクリプトを実行すると、
#   「Create Unsafe Agents」としてハーネスに拒否される場合があります。
#   その場合はローカル環境やCIジョブなど、ネストしたエージェント起動が許可される場所で
#   実行してください。
#
# 使い方:
#   ./run_pipeline.sh [--dry-run] <target-repo-path-or-url> [output_dir]
#
#   --dry-run  : 実際にはコマンドを実行せず、実行される内容だけを表示する

set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  echo "usage: $0 [--dry-run] <target-repo-path-or-url> [output_dir]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
WORKDIR="$(mktemp -d)"
CLEANUP_WORKDIR=0

run() {
  echo "+ $*"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    "$@"
  fi
}

# --- 1. 監査対象のリポジトリを解決する -------------------------------------
if [[ "$TARGET" =~ ^(https?://|git@) ]]; then
  REPO_NAME="$(basename "$TARGET" .git)"
  TARGET_DIR="$WORKDIR/$REPO_NAME"
  CLEANUP_WORKDIR=1
  run git clone --depth 1 "$TARGET" "$TARGET_DIR"
else
  TARGET_DIR="$(cd "$TARGET" && pwd)"
  REPO_NAME="$(basename "$TARGET_DIR")"
fi

OUTPUT_DIR="${2:-$SCRIPT_DIR/audit-runs/${REPO_NAME}-${TIMESTAMP}}"
mkdir -p "$OUTPUT_DIR"

echo "対象リポジトリ: $TARGET_DIR"
echo "出力先        : $OUTPUT_DIR"

# --- 2. security-audit-skill をインストール（未導入なら） -------------------
run npx --yes skills add https://github.com/cloudflare/security-audit-skill \
  --skill security-audit

# --- 3. Claude Code をヘッドレス実行して監査 -> findings.json 生成 ----------
FINDINGS_JSON="$OUTPUT_DIR/findings.json"
AUDIT_LOG="$OUTPUT_DIR/claude_audit_run.json"

AUDIT_CMD=(claude -p
  "security audit this codebase. Write the resulting findings.json (and coverage-ledger.json if produced) into ${OUTPUT_DIR}"
  --add-dir "$TARGET_DIR"
  --permission-mode bypassPermissions
  --output-format json)

echo "+ ${AUDIT_CMD[*]} > $AUDIT_LOG"
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] findings.json の検証・翻訳ステップはスキップします。"
  exit 0
fi
"${AUDIT_CMD[@]}" > "$AUDIT_LOG"

if [[ ! -f "$FINDINGS_JSON" ]]; then
  echo "警告: ${FINDINGS_JSON} が見つかりません。" >&2
  echo "claude の出力先指示が効かなかった可能性があります。" >&2
  echo "既定の出力先 ~/security-audit-skill/${REPO_NAME}/run-*/findings.json も確認してください。" >&2
  exit 1
fi

# --- 4. findings.json をスキーマ検証（validate-findings.cjs があれば） ------
VALIDATOR="$(find "$HOME" -maxdepth 6 -name validate-findings.cjs 2>/dev/null | head -1 || true)"
if [[ -n "$VALIDATOR" ]]; then
  run node "$VALIDATOR" "$FINDINGS_JSON"
else
  echo "警告: validate-findings.cjs が見つからなかったため、スキーマ検証をスキップしました。" >&2
fi

# --- 5. 日本語レポートに変換 -------------------------------------------------
REPORT_JA="$OUTPUT_DIR/report_ja_llm.md"
run bash -c "python3 '$SCRIPT_DIR/translate_findings_llm.py' '$FINDINGS_JSON' > '$REPORT_JA'"

echo "完了しました: $REPORT_JA"
