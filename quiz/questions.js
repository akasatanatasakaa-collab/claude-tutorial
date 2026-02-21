// クイズの問題データ
const quizQuestions = [
    {
        question: "Claude Code で会話をリセットするコマンドはどれ？",
        choices: ["/clear", "/reset", "/delete", "/new"],
        answer: 0,
        explanation: "/clear は会話を完全リセットします。元に戻せないので注意！"
    },
    {
        question: "会話を要約して短くするコマンドはどれ？",
        choices: ["/summary", "/short", "/compact", "/compress"],
        answer: 2,
        explanation: "/compact は会話を要約して圧縮します。文脈は残るので、迷ったらこちらが安全です。"
    },
    {
        question: "「Allow Read」の許可メッセージは何を意味する？",
        choices: ["ファイルを削除する", "ファイルを読む", "ファイルを作成する", "コマンドを実行する"],
        answer: 1,
        explanation: "Allow Read はファイルの内容を読む許可です。読むだけなので安全です。"
    },
    {
        question: "CLAUDE.md はどこに置くとプロジェクト専用のルールになる？",
        choices: ["ホームフォルダ", "デスクトップ", "プロジェクトのルート（一番上）", "どこでも同じ"],
        answer: 2,
        explanation: "プロジェクトのルートに置くとそのプロジェクト専用、~/.claude/CLAUDE.md に置くと全プロジェクト共通です。"
    },
    {
        question: "Git でセーブポイントを作ることを何という？",
        choices: ["プッシュ", "プル", "コミット", "ブランチ"],
        answer: 2,
        explanation: "コミット（commit）はセーブポイントを作ることです。いつでもその時点に戻れます。"
    },
    {
        question: "Git と GitHub の違いは？",
        choices: [
            "同じもの",
            "Git=PC上のセーブ管理、GitHub=ネット上の保管サービス",
            "Git=ネット上、GitHub=PC上",
            "GitはWindows用、GitHubはMac用"
        ],
        answer: 1,
        explanation: "Gitは自分のPC上でセーブポイントを管理するツール、GitHubはそのデータをネット上に保管するサービスです。"
    },
    {
        question: "MCPとは何のこと？",
        choices: [
            "プログラミング言語の一種",
            "Claude Code の有料プラン",
            "追加機能をつなげる仕組み",
            "ファイル圧縮ツール"
        ],
        answer: 2,
        explanation: "MCPは追加機能をつなげる仕組みです。スマホにアプリを入れるイメージです。"
    },
    {
        question: "VSCode でコードを選択して Claude Code に質問すると何が起きる？",
        choices: [
            "エラーになる",
            "選択したコードが自動で送られて質問できる",
            "ファイルが削除される",
            "何も起きない"
        ],
        answer: 1,
        explanation: "エディタでコードを選択すると、その部分が自動でClaude Codeに送られます。「これ何？」と聞くだけで説明してもらえます。"
    },
    {
        question: "ブランチとは何のこと？",
        choices: [
            "ファイルを削除する機能",
            "本体に影響を与えず別の作業をする枝分かれ",
            "コミットを取り消す機能",
            "ファイルを圧縮する機能"
        ],
        answer: 1,
        explanation: "ブランチは本体（master）に影響を与えずに別の作業ができる枝分かれ機能です。"
    },
    {
        question: "Claude Code でフォルダを開き直すと会話履歴はどうなる？",
        choices: [
            "そのまま残る",
            "半分だけ残る",
            "消える（でもコードとGitは残る）",
            "すべて完全に消える"
        ],
        answer: 2,
        explanation: "会話履歴はセッション限りなので消えますが、コードやGitの履歴はちゃんと残っています。安心！"
    }
];
