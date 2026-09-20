#!/usr/bin/env python3
"""
security-audit-skill が出力する findings.json を、
非エンジニアでも読める日本語レポート（Markdown）に変換するプロトタイプ。

使い方:
    python3 translate_findings_ja.py findings.json > report_ja.md

これは「バイブコーダー向けセキュリティ監査SaaS構想」の核となる変換レイヤーの
最小プロトタイプです。実際のSaaSでは、この部分をLLM呼び出しに置き換えて
（各findingの内容をもとに、もっと柔軟な日本語説明を生成する）拡張していきます。
"""
import json
import sys

SEVERITY_JA = {
    "critical": ("🔴 緊急", "今すぐ対応が必要です。放置すると実害が出る可能性が高いレベルです。"),
    "high": ("🟠 重要", "できるだけ早く対応することを強くおすすめします。"),
    "medium": ("🟡 注意", "早めに直しておきたいレベルです。"),
    "low": ("🟢 軽微", "余裕があるときに直せば十分です。"),
    "informational": ("ℹ️ 参考情報", "すぐに危険ではありませんが、知っておくと良い情報です。"),
}

VERDICT_JA = {
    "confirmed": "確認済みの問題",
    "needs_validation": "要確認（自動判定できなかった疑わしい箇所）",
    "rejected": "調査した結果、問題なしと判断",
}


def render_confirmed(item, index):
    sev_key = item["severity"]["overall_severity"]
    sev_label, sev_note = SEVERITY_JA.get(sev_key, (sev_key, ""))
    files = sorted({t["file"] for t in item.get("trace", [])})
    lines = []
    lines.append(f"## {index}. {sev_label}：{item['title']}")
    lines.append("")
    lines.append(f"**何が起きているか**：{item['description']}")
    lines.append("")
    lines.append(f"**なぜ危ないか**：{sev_note}")
    lines.append("")
    lines.append(f"**関係するファイル**：{', '.join(files) if files else '不明'}")
    lines.append("")
    remediation = item.get("remediation", {})
    if remediation.get("strategy"):
        lines.append(f"**直し方（ざっくり）**：{remediation['strategy']}")
        lines.append("")
    code_changes = remediation.get("code_changes", [])
    if code_changes:
        lines.append("**修正コードの例**：")
        for cc in code_changes:
            lines.append(f"- `{cc['file_name']}`")
            lines.append("```")
            lines.append(cc["fixed_code"])
            lines.append("```")
        lines.append("")
    lines.append("<details><summary>技術者向けの詳細（クリックで開く）</summary>")
    lines.append("")
    lines.append(f"- root cause: {item.get('root_cause', '')}")
    exec_info = item.get("execution", {})
    if exec_info.get("payloads"):
        lines.append(f"- 再現方法: {'; '.join(exec_info['payloads'])}")
    lines.append(f"- confidence: {item.get('confidence', {}).get('score', '')}"
                  f"（{item.get('confidence', {}).get('reason', '')}）")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    return "\n".join(lines)


def render_needs_validation(item, index):
    lines = []
    lines.append(f"## {index}. ⚪ 要確認：{item['title']}")
    lines.append("")
    lines.append(f"**内容**：{item['description']}")
    lines.append("")
    blockers = item.get("blockers", [])
    if blockers:
        lines.append(f"**自動判定できなかった理由**：{'; '.join(blockers)}")
        lines.append("")
    lines.append("**人の目でのチェックをおすすめします。**")
    lines.append("")
    return "\n".join(lines)


def main():
    if len(sys.argv) != 2:
        print("usage: translate_findings_ja.py findings.json", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        findings = json.load(f)

    confirmed = [f for f in findings if f["verdict"] == "confirmed"]
    needs_validation = [f for f in findings if f["verdict"] == "needs_validation"]

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
    confirmed.sort(key=lambda f: severity_order.get(f["severity"]["overall_severity"], 99))

    out = []
    out.append("# セキュリティ監査レポート（かんたん版）")
    out.append("")
    out.append(f"確認済みの問題: **{len(confirmed)}件** ／ 要確認: **{len(needs_validation)}件**")
    out.append("")
    if confirmed:
        crit = sum(1 for f in confirmed if f["severity"]["overall_severity"] in ("critical", "high"))
        if crit:
            out.append(f"⚠️ このうち **{crit}件** は緊急〜重要レベルです。まずここから対応してください。")
            out.append("")

    out.append("---")
    out.append("")
    for i, item in enumerate(confirmed, 1):
        out.append(render_confirmed(item, i))
    for i, item in enumerate(needs_validation, len(confirmed) + 1):
        out.append(render_needs_validation(item, i))

    print("\n".join(out))


if __name__ == "__main__":
    main()
