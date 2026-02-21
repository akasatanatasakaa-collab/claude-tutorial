// クイズの状態管理
let currentQuestion = 0;
let score = 0;
let answers = []; // 回答の記録（復習用）

// スタート画面に問題数を表示
document.querySelector('.question-count').textContent =
    `全${quizQuestions.length}問`;

// クイズ開始
function startQuiz() {
    document.getElementById('start-screen').classList.add('hidden');
    document.getElementById('quiz-screen').classList.remove('hidden');
    showQuestion();
}

// 問題を表示
function showQuestion() {
    const q = quizQuestions[currentQuestion];
    const total = quizQuestions.length;

    // 進捗を更新
    document.getElementById('progress-text').textContent =
        `${currentQuestion + 1} / ${total}`;
    document.getElementById('progress-fill').style.width =
        `${((currentQuestion + 1) / total) * 100}%`;

    // 問題文を表示
    document.getElementById('question-text').textContent = q.question;

    // 選択肢を表示
    const choicesDiv = document.getElementById('choices');
    choicesDiv.innerHTML = '';
    q.choices.forEach((choice, index) => {
        const btn = document.createElement('button');
        btn.className = 'choice-btn';
        btn.textContent = choice;
        btn.onclick = () => selectAnswer(index);
        choicesDiv.appendChild(btn);
    });

    // フィードバックと次へボタンを隠す
    document.getElementById('feedback').classList.add('hidden');
    document.getElementById('next-btn').classList.add('hidden');
}

// 回答を選択
function selectAnswer(selected) {
    const q = quizQuestions[currentQuestion];
    const isCorrect = selected === q.answer;
    const buttons = document.querySelectorAll('.choice-btn');

    // すべてのボタンを無効化
    buttons.forEach((btn, index) => {
        btn.classList.add('disabled');
        btn.onclick = null;
        if (index === q.answer) {
            btn.classList.add('correct');
        }
        if (index === selected && !isCorrect) {
            btn.classList.add('wrong');
        }
    });

    // スコア更新
    if (isCorrect) score++;

    // 回答を記録
    answers.push({
        question: q.question,
        selected: q.choices[selected],
        correct: q.choices[q.answer],
        isCorrect: isCorrect,
        explanation: q.explanation
    });

    // フィードバック表示
    const feedback = document.getElementById('feedback');
    feedback.classList.remove('hidden', 'correct', 'wrong');
    if (isCorrect) {
        feedback.classList.add('correct');
        feedback.textContent = `⭕ 正解！ ${q.explanation}`;
    } else {
        feedback.classList.add('wrong');
        feedback.textContent = `❌ 不正解… ${q.explanation}`;
    }

    // 次へボタン表示
    document.getElementById('next-btn').classList.remove('hidden');
}

// 次の問題へ
function nextQuestion() {
    currentQuestion++;
    if (currentQuestion < quizQuestions.length) {
        showQuestion();
    } else {
        showResult();
    }
}

// 結果画面を表示
function showResult() {
    document.getElementById('quiz-screen').classList.add('hidden');
    document.getElementById('result-screen').classList.remove('hidden');

    const total = quizQuestions.length;
    document.getElementById('score').textContent = score;
    document.getElementById('total').textContent = total;

    // スコアに応じたメッセージ
    const percentage = (score / total) * 100;
    const messageEl = document.getElementById('score-message');
    if (percentage === 100) {
        messageEl.textContent = '🎉 パーフェクト！完璧です！';
    } else if (percentage >= 80) {
        messageEl.textContent = '🌟 すばらしい！よく覚えていますね！';
    } else if (percentage >= 60) {
        messageEl.textContent = '👍 いい感じ！もう少しで完璧！';
    } else if (percentage >= 40) {
        messageEl.textContent = '📚 まずまず。復習すればすぐ上達します！';
    } else {
        messageEl.textContent = '💪 これから！チュートリアルを見直してみよう！';
    }

    // 復習セクション
    const reviewDiv = document.getElementById('review');
    reviewDiv.innerHTML = '<h3 style="margin-bottom: 12px; color: #fff;">📝 復習</h3>';
    answers.forEach((a, i) => {
        const item = document.createElement('div');
        item.className = `review-item${a.isCorrect ? '' : ' wrong-answer'}`;
        item.innerHTML = `
            <div class="review-question">${i + 1}. ${a.question}</div>
            <div class="review-answer">
                ${a.isCorrect ? '⭕' : '❌'} あなたの答え: ${a.selected}
                ${a.isCorrect ? '' : `<br>✅ 正解: ${a.correct}`}
            </div>
        `;
        reviewDiv.appendChild(item);
    });
}
