#!/usr/bin/env python3
"""
security-audit-skill の findings.json を、Claude API 呼び出しで
「非エンジニアが読める自然な日本語」に本当に翻訳するバージョン。

前のプロトタイプ（translate_findings_ja.py）は見出しや重要度ラベルだけを
日本語化した"ガワだけ"のものでした。こちらは finding 本文
（description / root_cause / remediation）を Claude にそのつど渡して、
非エンジニア向けに書き直させます。

使い方（本番・実際にAPIを叩く）:
    export ANTHROPIC_API_KEY=sk-ant-xxxx
    pip install -r requirements.txt
    python3 translate_findings_llm.py demo/findings.json > demo/output/report_ja_llm.md

このセッションにはAPIキーが無いため、ANTHROPIC_API_KEY が未設定のときは
--mock 相当のフォールバック（事前に用意した高品質な翻訳例）を使い、
「実際にAPIを呼んだ場合に返ってくるはずの内容」を確認できるようにしてあります。
本番運用ではこの MOCK_TRANSLATIONS 辞書は使わず、実際に毎回 Claude に投げます。
"""
import json
import os
import sys

SEVERITY_JA = {
    "critical": ("🔴 緊急", "今すぐ対応が必要です。放置すると実害が出る可能性が高いレベルです。"),
    "high": ("🟠 重要", "できるだけ早く対応することを強くおすすめします。"),
    "medium": ("🟡 注意", "早めに直しておきたいレベルです。"),
    "low": ("🟢 軽微", "余裕があるときに直せば十分です。"),
    "informational": ("ℹ️ 参考情報", "すぐに危険ではありませんが、知っておくと良い情報です。"),
}

TRANSLATE_PROMPT = """あなたはセキュリティの専門家ではない個人開発者（Lovableやバイブコーディングでアプリを作っている人）に、
セキュリティ監査で見つかった問題を説明する役目です。

以下はセキュリティ監査ツールが出力した、1件の脆弱性に関する技術情報（英語）です。
これを読んで、非エンジニアにも伝わる自然な日本語で書き直してください。専門用語は避けるか、
使う場合は一言で補足してください。誇張せず、かつ危険度が正しく伝わるようにしてください。

# 技術情報
タイトル: {title}
説明: {description}
根本原因: {root_cause}
修正方針: {remediation_strategy}
重要度: {severity}（可能性: {likelihood_reason} / 影響: {impact_reason}）

# 出力形式
次のキーを持つJSONだけを出力してください（説明文や前置きは不要）:
{{
  "title_ja": "...",
  "description_ja": "...(2〜3文、何が起きていてなぜ問題かを平易な日本語で)",
  "why_it_matters_ja": "...(1〜2文、放置した場合に具体的に何が起こりうるか)",
  "fix_ja": "...(1〜2文、エンジニアでなくても『何を頼めばいいか』が分かる修正方針)"
}}
"""

# ANTHROPIC_API_KEY が無い環境向けのフォールバック。
# 本番ではこの辞書は使わず、常に実際のAPI呼び出し結果を使う。
MOCK_TRANSLATIONS = {
    "app.js:searchEndpoint:sql-injection": {
        "title_ja": "商品検索機能から、データベースの中身を丸ごと盗める・壊せる問題",
        "description_ja": (
            "商品を検索する機能が、ユーザーが入力した検索ワードをそのままデータベースへの命令文に"
            "組み込んでしまっています。そのため、検索ワードの入力欄に特殊な文字列を入れるだけで、"
            "本来見えるはずのない情報（他のユーザーのパスワードなど）を取り出したり、"
            "データを書き換えたりできてしまいます。"
        ),
        "why_it_matters_ja": (
            "ログインすら不要で、誰でも検索ボックスから攻撃できてしまいます。放置すると、"
            "顧客情報の流出やデータベース破壊など、サービス停止レベルの被害につながる可能性があります。"
        ),
        "fix_ja": (
            "「検索ワードを直接SQL文に埋め込まず、必ず“プレースホルダー”という安全な仕組みを使って"
            "データベースに渡すように直してほしい」とエンジニア（またはAIコーディングツール）に依頼してください。"
        ),
    },
    "app.js:hardcoded-secret:rakuten-api-key": {
        "title_ja": "外部サービスの秘密の鍵が、誰でも見られる形で漏れている問題",
        "description_ja": (
            "楽天など外部サービスに接続するための秘密の鍵（APIキー）が、プログラムのコードに"
            "そのまま書き込まれています。さらに、その鍵が特定のページのアクセス結果として"
            "誰にでもそのまま表示されてしまう作りになっています。"
        ),
        "why_it_matters_ja": (
            "この鍵を盗んだ第三者が、あなたのアカウントになりすまして外部サービスを操作したり、"
            "利用料金を勝手に発生させたりする恐れがあります。コードを見られただけでも漏れてしまいます。"
        ),
        "fix_ja": (
            "「鍵はコードに直接書かず、環境変数という仕組みに移し、レスポンスにも絶対に含めないでほしい。"
            "あわせて、今使っている鍵はすでに漏れている前提で、発行し直してほしい」と依頼してください。"
        ),
    },
}


def call_llm_or_mock(finding):
    fp = finding["fingerprint"]
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if api_key:
        try:
            import anthropic  # pip install anthropic
        except ImportError:
            print("警告: anthropic パッケージが無いのでモックにフォールバックします "
                  "(pip install anthropic)", file=sys.stderr)
            return MOCK_TRANSLATIONS.get(fp), False

        client = anthropic.Anthropic(api_key=api_key)
        sev = finding["severity"]
        prompt = TRANSLATE_PROMPT.format(
            title=finding["title"],
            description=finding["description"],
            root_cause=finding.get("root_cause", ""),
            remediation_strategy=finding.get("remediation", {}).get("strategy", ""),
            severity=sev["overall_severity"],
            likelihood_reason=sev["likelihood"]["reason"],
            impact_reason=sev["impact"]["reason"],
        )
        resp = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        # 応答からJSON部分だけを抜き出す
        start, end = text.find("{"), text.rfind("}")
        return json.loads(text[start:end + 1]), True

    # APIキーが無いので、事前に用意した「実際に呼んだ場合に相当する」翻訳を使う
    return MOCK_TRANSLATIONS.get(fp), False


def render(finding, ja, index, used_real_api):
    sev_key = finding["severity"]["overall_severity"]
    sev_label, _ = SEVERITY_JA.get(sev_key, (sev_key, ""))
    tag = "🟢 実際のAPI応答" if used_real_api else "⚪ モック（キー未設定のためのサンプル訳）"
    lines = [
        f"## {index}. {sev_label}：{ja['title_ja']}",
        "",
        f"*[{tag}]*",
        "",
        f"**何が起きているか**：{ja['description_ja']}",
        "",
        f"**放置するとどうなるか**：{ja['why_it_matters_ja']}",
        "",
        f"**どう直せばいいか**：{ja['fix_ja']}",
        "",
        f"**対象ファイル**：{', '.join(sorted({t['file'] for t in finding.get('trace', [])}))}",
        "",
    ]
    return "\n".join(lines)


def main():
    if len(sys.argv) != 2:
        print("usage: translate_findings_llm.py findings.json", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        findings = [x for x in json.load(f) if x["verdict"] == "confirmed"]

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
    findings.sort(key=lambda x: severity_order.get(x["severity"]["overall_severity"], 99))

    out = ["# セキュリティ監査レポート（LLM翻訳版）", "", f"確認済みの問題: **{len(findings)}件**", "", "---", ""]
    for i, finding in enumerate(findings, 1):
        ja, used_real_api = call_llm_or_mock(finding)
        if ja is None:
            continue
        out.append(render(finding, ja, i, used_real_api))
    print("\n".join(out))


if __name__ == "__main__":
    main()
